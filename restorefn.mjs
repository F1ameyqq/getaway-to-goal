// 全量重置：导航到平台 → reload → 选书 → 选目录 → 翻到 题目页/答案页
// 返回 { cur, counts, pages, timing }，cur 即平台给的「当前题目」号
// 页码默认 28/174（p28 那批的老约定），录别的页时显式传 restore({ qPage: 33, aPage: 175 })
//
// 2026-10-27 优化：选书/选目录/等编辑器这些「固定等 N 秒」全部换成条件轮询。
// 条件超时抛的仍然是原来的错误文案（AGENT_PROMPT 的故障对照表按这些文案查）。
// 翻页那两次 4s 故意保留：画布是否真的画完没有可靠的 DOM 信号，拿不准就先不动。
import { P } from "./config.mjs";

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

export async function restore({ qPage = 28, aPage = 174 } = {}) {
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

  // page.reload() 默认只等 15s，平台偶尔要 20–40s 才 complete。
  // 超时不代表失败（reload 已经发起了），所以吞掉超时，改为轮询 readyState。
  try {
    await page.reload();
  } catch (e) {
    if (!/timed out/i.test(String(e))) throw e;
  }
  mark("reload");
  await until(() => page.evaluate(() => document.readyState === "complete"), 45000, 250);
  mark("ready");

  // 选书：等按钮真的出现再点，不再固定等 2s+3s。
  const bookPos = await until(() => posOf("选择书籍"), 30000, 250);
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
        return ins.length >= 2 && cs.length >= 2;
      }),
    30000,
    200
  );
  mark("dir_ready");
  if (!ready) throw new Error("目录加载失败：页码输入框 / 画布未出现");

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

  async function gotoPage(pos, n, markKey) {
    // 已经在这一页就不要再翻（reload 后平台可能自己恢复上次页码）。
    let v0 = pos.v;
    try {
      v0 = await page.evaluate((i) => {
        const e = [...document.querySelectorAll("input")].filter((x) => x.getBoundingClientRect().x > 0)[i];
        return e ? e.value : null;
      }, pos.idx);
    } catch (e) {
      /* 保持初值 */
    }
    if (String(v0) === String(n)) {
      // 和原来一样给画布 4s 绘制时间，只是省掉了输入动作。
      await delay(4000);
      mark(markKey);
      return;
    }

    await page.mouse.click(pos.x, pos.y);
    await delay(400);
    await page.keyboard.down("Control");
    await page.keyboard.press("a");
    await page.keyboard.up("Control");
    await delay(200);
    await page.keyboard.type(String(n), { delay: 90 });
    await page.keyboard.press("Enter");
    await page.waitForTimeout(4000);
    mark(markKey);
  }

  await gotoPage({ ...pageInputs[0], idx: 0 }, qPage, "flip_q");
  await gotoPage({ ...pageInputs[1], idx: 1 }, aPage, "flip_a");

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
  return { ...st, timing };
}
