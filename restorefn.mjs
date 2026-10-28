// 全量重置：导航到平台 → reload → 选书 → 选目录 → 翻到 题目页/答案页
// 返回 { cur, counts, pages, timing }，cur 即平台给的「当前题目」号
// 页码默认 28/174（p28 那批的老约定），录别的页时显式传 restore({ qPage: 33, aPage: 175 })
//
// 2026-10-27 优化：选书/选目录/等编辑器这些「固定等 N 秒」全部换成条件轮询。
// 2026-10-28 优化：reload 改走 location.reload + 新文档信号（不再等 load，省约 9s）；
//   翻页改用画布像素哈希（变化 + 连续稳定），不再固定等 4s。
// 条件超时抛的仍然是原来的错误文案（AGENT_PROMPT 的故障对照表按这些文案查）。
import { P } from "./config.mjs";
import { norm, requireLessonIndex, assertSelectedLesson } from "./ordercheck.mjs";
import { parseTree, requireLesson } from "./dirtree.mjs";

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

// 轮询到条件为真。evaluate 在导航中会抛「context destroyed」，一律当作「还没好」。
// 超时返回 null，由调用方抛出原有的错误文案。
async function until(fn, timeout, interval = 120) {
  const end = Date.now() + timeout;
  for (;;) {
    let v = null;
    try {
      v = await fn();
    } catch (e) {
      v = null;
    }
    if (v) return v;
    if (Date.now() >= end) return null;
    await delay(interval);
  }
}

export async function restore({ qPage = 28, aPage = 174, lesson = null, verbose = false } = {}) {
  // 落点必须由调用方显式指定（pages json 的 lesson 字段）。禁止回落到旧题号算术。
  if (!lesson) throw new Error("restore: 未指定 lesson（课时名）—— 拒绝按题号推算落点");
  const task = await taskSpace(P.taskSpace);
  const page = task.page(P.page);
  const T0 = Date.now();
  const timing = {};
  const mark = (k) => {
    timing[k] = Date.now() - T0;
  };

  const posOf = (txt) =>
    page.evaluate((t) => {
      const e = [...document.querySelectorAll("button,span,div")]
        .filter((x) => x.getBoundingClientRect().width > 0)
        .find((x) => x.innerText.trim() === t);
      if (!e) return null;
      const r = e.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    }, txt);

  // 新开的 task space 会停在 chrome://new-tab-page，reload 救不回来，必须先导航。
  // 这是 2026-10-27 第一次真实提交时踩到的：restore 一直报「not found: 选择书籍」。
  let url0 = "";
  try {
    url0 = await page.evaluate(() => location.href);
  } catch (e) {
    url0 = "";
  }
  if (!/^https?:/.test(url0)) {
    await page.goto(P.url);
    await until(() => posOf("选择书籍"), 30000, 250);
  }
  mark("nav");

  // 2026-10-28 实测：page.reload() 要等 load 事件，平台有个慢资源把它拖到 9.5s，
  // 而「选择书籍」按钮在新文档里约 170ms 就出现了。
  // 改成 location.reload() + 等「新文档（timeOrigin 变了）+ 按钮出现」。
  // 快路径没生效（例如 beforeunload 拦了）就退回原来的 page.reload()。
  const origin0 = await page.evaluate(() => performance.timeOrigin).catch(() => null);
  let bookPos = null;
  if (origin0 !== null) {
    try {
      await Promise.race([page.evaluate(() => location.reload()).catch(() => {}), delay(3000)]);
    } catch (e) {
      /* 导航中 context destroyed 是正常现象 */
    }
    bookPos = await until(
      async () => {
        const o = await page.evaluate(() => performance.timeOrigin).catch(() => null);
        if (o === null || o === origin0) return null; // 还是旧文档
        return await posOf("选择书籍");
      },
      5000,
      100
    );
  }
  if (!bookPos) {
    try {
      await page.reload();
    } catch (e) {
      if (!/timed out/i.test(String(e))) throw e;
    }
    bookPos = await until(() => posOf("选择书籍"), 30000, 250);
  }
  mark("reload");
  if (!bookPos) throw new Error("not found: 选择书籍");
  await page.mouse.click(bookPos.x, bookPos.y);
  mark("book_open");

  // 等书表里出现目标 fileId 那一行，再点「选择」。
  const pickPos = await until(
    () =>
      page.evaluate((fid) => {
        const row = [...document.querySelectorAll(".el-table__row")].find((e) => e.innerText.includes(fid));
        if (!row) return null;
        const b = [...row.querySelectorAll("button")].find((e) => e.innerText.trim() === "选择");
        if (!b) return null;
        const r = b.getBoundingClientRect();
        return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
      }, P.fileId),
    30000,
    200
  );
  if (!pickPos) throw new Error("no 选择 button for fileId=" + P.fileId);
  await page.mouse.click(pickPos.x, pickPos.y);
  mark("book_pick");

  // 等目录树节点出现（选书后要拉目录，固定 6s 经常不够也经常浪费）。
  const hit = await until(
    () =>
      page.evaluate((node) => {
        const e = [...document.querySelectorAll(".el-tree-node__content")].find(
          (x) => x.innerText.replace(/\s+/g, " ").trim() === node
        );
        if (!e) return null;
        e.scrollIntoView({ block: "center" });
        return true;
      }, P.dirNode),
    30000,
    200
  );
  if (!hit) throw new Error("目录节点未找到: " + P.dirNode);

  // scrollIntoView 若被 CSS 设成平滑滚动，位置要几帧才稳定：两次采样一致再点。
  // 超时也用最后一次位置，不要因为「没完全停稳」就当成节点不存在。
  let prev = null;
  let last = null;
  const nodePos =
    (await until(
      async () => {
        const r = await page.evaluate((dirNode) => {
          const e = [...document.querySelectorAll(".el-tree-node__content")].find(
            (x) => x.innerText.replace(/\s+/g, " ").trim() === dirNode
          );
          if (!e) return null;
          const b = e.getBoundingClientRect();
          return { x: Math.round(b.x + 40), y: Math.round(b.y + b.height / 2) };
        }, P.dirNode);
        if (!r) return null;
        last = r;
        const same = prev && prev.x === r.x && prev.y === r.y;
        prev = r;
        return same ? r : null;
      },
      4000,
      80
    )) || last;
  if (!nodePos) throw new Error("目录节点未找到: " + P.dirNode);
  await page.mouse.click(nodePos.x, nodePos.y);
  mark("dir_click");

  // 目录点击后平台要拉该目录的页数据。原来固定等 3s：这里留 1.2s 下限，
  // 再等编辑器结构就绪（两个页码输入框 + 两块画布）。
  await delay(1200);
  const ready = await until(
    () =>
      page.evaluate(() => {
        const ins = [...document.querySelectorAll("input")].filter((i) => i.getBoundingClientRect().x > 0);
        const cs = document.querySelectorAll("canvas.pdf-canvas");
        // 输入框存在 ≠ 目录数据已拉到：刚 reload 时两个页码输入框是空的，
        // 这时翻页不会生效（画布一直停在第一页）。必须有页码才算就绪。
        return ins.length >= 2 && cs.length >= 2 && ins[0].value.trim() !== "" && ins[1].value.trim() !== "";
      }),
    30000,
    200
  );
  mark("dir_ready");
  if (!ready) throw new Error("目录加载失败：页码输入框 / 画布未出现");

  // 2026-10-28 实测：平台只在「选中最子级目录」后才允许标注 ——
  // 否则点 题目(Q) 只弹一句「请先选择左侧的目录！」就返回（Au() 的 !Ct.value 分支），
  // 画布收得到 mousedown/mousemove，但一个框都不会登记（counts 恒为 0）。
  // 坑：点 .el-tree-node__content 的 x+40 往往正好落在展开箭头 <i class="el-tree-node__expand">
  // 上，箭头自带 click.stop，节点根本不会被选中。必须点标签文字本体。
  //
  // 2026-10-28 事故复盘（务必别改回去）：插题落点 = 「选中的最子级目录（课时）」，
  // 跟 cur、跟 OCR 的 question_order 都无关。旧实现按「该课时末尾题号 = cur-1」挑目录，
  // 一旦前后两页跨课时、或库里有一条畸形记录（如 order 95 两个题目框 0 答案框），就稳定选错，
  // 且每次都自检通过。现在改为：调用方显式传 lesson，按名字精确选中；点完回读 is-current 节点
  // 文本必须 === lesson，否则立刻中止。不再用题号算术挑选。
  const leaf = await page.evaluate(() => {
    const txt = (n) => {
      const c = n.querySelector(":scope > .el-tree-node__content");
      // 用 textContent：课时折叠时 innerText 是空串，textContent 仍有内容。
      return c ? (c.textContent || "").replace(/\s+/g, " ").trim() : "";
    };
    const leafDirs = () => {
      const out = [];
      for (const n of document.querySelectorAll(".el-tree-node")) {
        const c = n.querySelector(":scope > .el-tree-node__content");
        if (!c || c.querySelector(".question-node")) continue; // 自身是题目节点
        const kids = [...n.querySelectorAll(":scope > .el-tree-node__children > .el-tree-node")];
        // 子节点里只要还有目录（非题目）节点，这一层就是章/父级，不是课时。
        const hasDirChild = kids.some((k) => {
          const kc = k.querySelector(":scope > .el-tree-node__content");
          return kc && !kc.querySelector(".question-node");
        });
        if (hasDirChild) continue;
        // 剩下的是叶子目录（课时）：要么子节点全是题目节点，要么一个子节点都没有（空课时）。
        out.push(n);
      }
      return out;
    };
    window.__leafDirs = leafDirs;
    // 目标课时可能折叠着：先把祖先逐层展开，否则点不到、也读不到坐标。
    window.__expandAncestors = (n) => {
      const anc = [];
      let p = n.parentElement && n.parentElement.closest(".el-tree-node");
      while (p) {
        anc.push(p);
        p = p.parentElement && p.parentElement.closest(".el-tree-node");
      }
      for (const a of anc.reverse()) {
        const kids = a.querySelector(":scope > .el-tree-node__children");
        const caret = a.querySelector(":scope > .el-tree-node__content .el-tree-node__expand-icon");
        if (kids && kids.getBoundingClientRect().height < 5 && caret) caret.click();
      }
    };
    const leaves = window.__leafDirs();
    const labels = leaves.map((n) => txt(n));
    // 每个课时下已挂的题目节点数。目标课时必须是 0，否则说明有残留。
    const qKids = leaves.map((n) =>
      [...n.querySelectorAll(":scope > .el-tree-node__children > .el-tree-node")].filter((k) => {
        const kc = k.querySelector(":scope > .el-tree-node__content");
        return kc && kc.querySelector(".question-node");
      }).length
    );
    const t = document.body.innerText.replace(/\s+/g, " ");
    const cur = (t.match(/当前题目[:：]\s*(\d+)/) || [])[1] || null;
    return { cur, labels, qKids };
  });
  if (!leaf.cur) throw new Error("读不到当前题目，无法确定插题落点");
  const dirIdx = requireLessonIndex(leaf.labels, lesson);
  const dirLabel = leaf.labels[dirIdx];
  await page.evaluate((i) => {
    const n = window.__leafDirs()[i];
    if (!n) throw new Error("目标课时节点消失");
    window.__expandAncestors(n);
    n.querySelector(":scope > .el-tree-node__content").scrollIntoView({ block: "center" });
  }, dirIdx);
  await delay(700);
  let prevDir = null;
  let lastDir = null;
  const labelPos =
    (await until(async () => {
      const r = await page.evaluate((i) => {
        const n = window.__leafDirs()[i];
        if (!n) return null;
        const c = n.querySelector(":scope > .el-tree-node__content");
        const b = c.getBoundingClientRect();
        if (b.width <= 0) return null;
        return { x: Math.round(b.x + Math.min(b.width / 2, 30)), y: Math.round(b.y + b.height / 2) };
      }, dirIdx);
      if (!r) return null;
      lastDir = r;
      const same = prevDir && prevDir.x === r.x && prevDir.y === r.y;
      prevDir = r;
      return same ? r : null;
    }, 4000, 150)) || lastDir;
  if (!labelPos) throw new Error("目标课时在滚动后不可见: " + dirLabel);
  await page.mouse.click(labelPos.x, labelPos.y);
  await delay(2200);

  // 落点自证（回读）：点完读 is-current 节点文本，必须 === 传入 lesson，否则立刻中止。
  const selLabel = await until(async () => {
    const s = await page.evaluate(() => {
      const n = document.querySelector(".el-tree-node.is-current");
      if (!n) return null;
      const c = n.querySelector(":scope > .el-tree-node__content");
      return c ? (c.textContent || "").replace(/\s+/g, " ").trim() : null;
    });
    return s || null;
  }, 3000, 150);
  if (!selLabel) throw new Error(`课时选中自检失败：点完「${lesson}」后读不到被选中节点`);
  assertSelectedLesson(selLabel, lesson);

  // 读出被选中课时的 directory_id（服务端标注接口用同一字段标识归属）。
  // 唯一权威来源是平台自己的目录接口，不从 DOM / Vue 内部结构反推（框架一升级就读不到）。
  // 读不到就返回 null；录入流程（pageRun）会在提交前因此中止，绝不在没有落点证据时提交。
  const dirInfo = await (async () => {
    try {
      const tok = await page.evaluate(() => JSON.parse(localStorage.getItem("user")).access_token);
      const r = await page.fetch(`/qieti/api/annotate_ocr/directory/get?file_id=${P.fileId}`, {
        headers: { authorization: "Bearer " + tok },
        timeout: 30000,
      });
      const nodes = parseTree(r.body);
      const hit = requireLesson(nodes, lesson);
      return { id: hit.id, qCount: hit.qCount, via: "api" };
    } catch (e) {
      return { id: null, qCount: null, via: "api-failed: " + e.message };
    }
  })();

  // 老路径：DOM / Vue 内部结构。接口不可用时兜底，只用来补 id，不作为主证据。
  const dirInfoDom = dirInfo.id !== null ? null : await page.evaluate(() => {
    const scalar = (v) => (v !== null && v !== undefined && String(v).trim() !== "") ? String(v).trim() : null;
    const numeric = (v) => (scalar(v) !== null && !Number.isNaN(Number(v))) ? String(v).trim() : null;
    const scan = (o) => {
      if (!o || typeof o !== "object") return null;
      for (const k of ["directory_id", "directoryId", "dir_id", "dirId", "directory", "dir", "folder_id", "folderId"]) {
        const v = scalar(o[k]);
        if (v !== null) return v;
      }
      for (const k of Object.keys(o)) {
        if (/^(id|uid|node_id|nodeId|key)$/i.test(k)) {
          const v = scalar(o[k]);
          if (v !== null) return v;
        }
      }
      return null;
    };
    const el = document.querySelector(".el-tree-node.is-current");
    if (!el) return { id: null, dump: "" };
    for (const e of [el, el.querySelector(":scope > .el-tree-node__content")]) {
      if (!e) continue;
      for (const a of e.attributes) {
        const v = numeric(a.value);
        if (v !== null && /id|key|dir/i.test(a.name)) return { id: v, dump: "attr " + a.name };
      }
    }
    const cands = [];
    const vue = el.__vue__;
    if (vue) {
      cands.push(vue.node && vue.node.data);
      cands.push(vue.data);
      cands.push(vue.node);
    }
    const v3 = el.__vueParentComponent;
    if (v3) {
      cands.push(v3.props && v3.props.node && v3.props.node.data);
      cands.push(v3.props && v3.props.data);
    }
    for (const o of cands) {
      const id = scan(o);
      if (id !== null) {
        let dump = "";
        try { dump = JSON.stringify(o).slice(0, 500); } catch (e) { dump = "[unserializable]"; }
        return { id, dump };
      }
    }
    return { id: null, dump: "" };
  });
  const dirResolved = dirInfo.id !== null ? dirInfo : { id: dirInfoDom.id, qCount: null, via: "dom: " + dirInfoDom.dump };
  if (process.env.RESTORE_TIMING)
    console.log("RESTORE_DIR " + JSON.stringify({ lesson: dirLabel, dirId: dirResolved.id, via: dirResolved.via.slice(0, 160), qCount: dirResolved.qCount }));
  mark("dir_select");

  const pageInputs = await page.evaluate(() =>
    [...document.querySelectorAll("input")]
      .filter((i) => i.getBoundingClientRect().x > 0)
      .map((i) => {
        const r = i.getBoundingClientRect();
        return {
          x: Math.round(r.x + r.width / 2),
          y: Math.round(r.y + r.height / 2),
          v: i.value,
        };
      })
  );
  if (pageInputs.length < 2) throw new Error("目录加载失败：找不到两个页码输入框");

  // 画布签名：三条横带、每 7 个像素取一个，返回哈希 + 墨迹计数。
  // 2026-10-28 实测：翻页后约 0.2s 画面变化、约 0.4s 稳定；固定等 4s 纯属浪费。
  // 画布读不到像素（缺失/被污染）时返回 null，调用方退回原来的固定等待。
  async function canvasSig(idx) {
    try {
      return await page.evaluate((i) => {
        const c = document.querySelectorAll("canvas.pdf-canvas")[i];
        if (!c) return null;
        let ctx = null;
        try {
          ctx = c.getContext("2d");
        } catch (e) {
          return null;
        }
        if (!ctx || !ctx.getImageData) return null;
        let h = 2166136261 >>> 0;
        let ink = 0;
        try {
          for (const frac of [0.2, 0.5, 0.8]) {
            const y = Math.min(Math.floor(c.height * frac), Math.max(0, c.height - 40));
            const d = ctx.getImageData(0, y, c.width, 40).data;
            for (let k = 0; k < d.length; k += 28) {
              const v = ((d[k] + d[k + 1] + d[k + 2]) / 3) | 0;
              if (v < 200) ink++;
              h = ((h ^ v) * 16777619) >>> 0;
            }
          }
        } catch (e) {
          return null;
        }
        return { h, ink };
      }, idx);
    } catch (e) {
      return null; // 导航中 context destroyed
    }
  }

  async function gotoPage(idx, n, markKey) {
    const pos = pageInputs[idx];
    // 已经在这一页就不要再翻（reload 后平台可能自己恢复上次页码）。
    let v0 = pos.v;
    try {
      const cur = await page.evaluate((i) => {
        const e = [...document.querySelectorAll("input")].filter((x) => x.getBoundingClientRect().x > 0)[i];
        return e ? e.value : null;
      }, idx);
      if (cur !== null) v0 = cur;
    } catch (e) {
      /* 保持初值 */
    }
    const already = String(v0) === String(n);
    const before = await canvasSig(idx);
    if (verbose) console.log(`GOTO[${idx}] n=${n} v0=${v0} already=${already} before=${JSON.stringify(before)}`);

    if (!already) {
      await page.mouse.click(pos.x, pos.y);
      await delay(400);
      await page.keyboard.down("Control");
      await page.keyboard.press("a");
      await page.keyboard.up("Control");
      await delay(200);
      await page.keyboard.type(String(n), { delay: 90 });
      await page.keyboard.press("Enter");
    }

    if (!before) {
      // 取不到像素就别猜，按老办法给画布 4s
      await delay(4000);
      mark(markKey);
      return;
    }

    let changed = already;
    let lastH = null;
    let same = 0;
    let ink = 0;
    let np = 0;
    const ok = await until(
      async () => {
        const s = await canvasSig(idx);
        if (verbose && np++ % 4 === 0) console.log(`  poll[${idx}] ${JSON.stringify(s)} changed=${changed} same=${same}`);
        if (!s || s.ink < 50) return null; // 空白/还没画
        ink = s.ink;
        if (!changed) {
          if (s.h !== before.h) changed = true;
          return null;
        }
        if (s.h === lastH) same++;
        else same = 0;
        lastH = s.h;
        // 翻页：连续 5 次采样一致；已在目标页：连续 3 次就够（重绘抖动会一直有，判太死会误报失败）
        return same >= (already ? 2 : 4) ? true : null;
      },
      already ? 10000 : 8000,
      100
    );
    mark(markKey);
    // 已经在目标页、画布也有内容，只是像素还在小幅变化：页码后面还会再校验一次，
    // 这里判失败只会让整页白跑一轮。放过去，但把情况打出来。
    if (!ok && already && ink >= 50) {
      console.log("WARN 画布像素仍在变化，按已就绪处理（已在目标页，ink=" + ink + "）");
      return;
    }
    if (!ok) throw new Error("翻页失败: 画布未就绪（" + (already ? "已在目标页" : n) + "）");
  }

  await gotoPage(0, qPage, "flip_q");
  await gotoPage(1, aPage, "flip_a");

  const st = await page.evaluate(() => {
    const t = document.body.innerText.replace(/\s+/g, " ");
    return {
      counts: (t.match(/题目框\s*(\d+)\s答案\s*(\d+)\s选项\s*(\d+)/) || []).slice(1),
      cur: (t.match(/当前题目[:：]\s*(\d+)/) || [])[1],
      pages: [...document.querySelectorAll("input")]
        .filter((i) => i.getBoundingClientRect().x > 0)
        .map((i) => i.value)
        .slice(0, 2),
    };
  });
  if (st.pages[0] !== String(qPage) || st.pages[1] !== String(aPage))
    throw new Error("翻页失败: " + JSON.stringify(st.pages));
  if (st.counts.some((v) => v !== "0")) throw new Error("重置后仍有残留框: " + JSON.stringify(st.counts));
  if (!st.cur) throw new Error("读不到当前题目");
  mark("state");

  // 计时只在显式要求时打一行，正常跑不增加输出。
  if (process.env.RESTORE_TIMING) console.log("RESTORE_TIMING " + JSON.stringify(timing));
  const domQ = leaf.qKids && Number.isFinite(leaf.qKids[dirIdx]) ? leaf.qKids[dirIdx] : null;
  // 题数以接口为准；接口挂了才用 DOM 数出来的。
  const dirQ = typeof dirResolved.qCount === "number" ? dirResolved.qCount : domQ;
  return { ...st, dirLabel, dirId: dirResolved.id, dirQ, lesson: dirLabel, timing };
}
