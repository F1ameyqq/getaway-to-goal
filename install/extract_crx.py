# 从 ego 的 .crx3 安装包里取出真正的 7z 载荷。
#
# 为什么需要三步：
#   1. crx3 = 12 字节头 + protobuf header + zip，zip 里只有一个文件
#      `mini_installer_uncompressed.exe`（Chromium 的迷你安装器）
#   2. 那个 exe 的某个偏移之后是 7z 数据，签名 37 7A BC AF 27 1C
#   3. 7z 里才是完整的 `Chrome-bin/<版本>/` 文件树
#
# 用法: python -I extract_crx.py <xxx.crx3> <输出 7z 路径>
import sys, io, os, zipfile

SIG = b"7z\xbc\xaf\x27\x1c"


class OffsetReader(io.RawIOBase):
    """把 [base, 文件末尾) 伪装成从 0 开始的完整文件，zipfile 才能找 EOCD。"""

    def __init__(self, fh, base, size):
        self.f, self.base, self.size, self.pos = fh, base, size, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, p, whence=0):
        if whence == 0:
            self.pos = p
        elif whence == 1:
            self.pos += p
        else:
            self.pos = self.size + p
        self.pos = max(0, min(self.pos, self.size))
        self.f.seek(self.base + self.pos)
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        data = self.f.read(n)
        memoryview(b)[: len(data)] = data
        self.pos += len(data)
        return len(data)


def find_sig(path):
    """分块找 7z 签名，避免把 600MB 一次读进内存。"""
    chunk = 8 << 20
    overlap = len(SIG) - 1
    prev, base = b"", 0
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                return -1
            data = prev + buf
            i = data.find(SIG)
            if i >= 0:
                return base - len(prev) + i
            prev = data[-overlap:]
            base += len(buf)


def read_cr24(src):
    with open(src, "rb") as f:
        magic = f.read(4)
        if magic != b"Cr24":
            sys.exit("不是 crx 文件: " + repr(magic))
        ver = int.from_bytes(f.read(4), "little")
        hlen = int.from_bytes(f.read(4), "little")
        f.seek(0, 2)
        return ver, hlen, 12 + hlen, f.tell()


def main():
    if len(sys.argv) != 3:
        sys.exit("用法: python -I extract_crx.py <xxx.crx3> <输出 7z 路径>")
    src, dst = sys.argv[1], sys.argv[2]

    ver, hlen, off, total = read_cr24(src)
    print("crx_version=%d header=%d zip_offset=%d" % (ver, hlen, off))

    tmp_exe = dst + ".mini.exe"
    try:
        with open(src, "rb") as f:
            stream = io.BufferedReader(OffsetReader(f, off, total - off), 1 << 20)
            with zipfile.ZipFile(stream) as z:
                names = z.namelist()
                print("zip_entries=%d name=%s" % (len(names), names[0]))
                if len(names) != 1:
                    sys.exit("预期 crx 里只有一个文件，实际 %d 个" % len(names))
                with z.open(names[0]) as fi, open(tmp_exe, "wb") as fo:
                    while True:
                        b = fi.read(1 << 20)
                        if not b:
                            break
                        fo.write(b)

        pos = find_sig(tmp_exe)
        if pos < 0:
            sys.exit("在 mini_installer 里找不到 7z 签名")
        with open(tmp_exe, "rb") as fi, open(dst, "wb") as fo:
            fi.seek(pos)
            while True:
                b = fi.read(1 << 20)
                if not b:
                    break
                fo.write(b)
        print(
            "mini_installer=%d bytes, 7z_at=%d, payload=%d bytes"
            % (os.path.getsize(tmp_exe), pos, os.path.getsize(dst))
        )
    finally:
        if os.path.exists(tmp_exe):
            os.remove(tmp_exe)


if __name__ == "__main__":
    main()
