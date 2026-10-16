// 版面分析：输出每页尺寸、每页从上到下的“跨栏带 / 双栏带”划分，以及逐行墨迹分布
// 用法: swift layout.swift <name>orig.pdf <name>_layout.json
// 单栏论文（多数页面正文横跨中缝）整页记为一个跨栏带，并在顶层写 "single": true；
// "ink" 是每 1pt 高一行的墨迹位掩码：页宽均分 32 格，第 k 位为 1 表示该行第 k 格有墨迹
import Foundation
import PDFKit
import CoreGraphics

let args = CommandLine.arguments
let doc = PDFDocument(url: URL(fileURLWithPath: args[1]))!
let S: CGFloat = 2.0   // 144 dpi
var pages: [[String: Any]] = []
var gutRatio: [Double] = []      // 每页有墨迹的行里，中缝也有墨迹的比例：单栏正文接近 1，双栏接近 0
var inkTop: [CGFloat] = [], inkBot: [CGFloat] = []

for pi in 0..<doc.pageCount {
    let page = doc.page(at: pi)!
    let box = page.bounds(for: .mediaBox)
    let W = Int(box.width * S), H = Int(box.height * S)
    let cs = CGColorSpaceCreateDeviceGray()
    let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W,
                        space: cs, bitmapInfo: CGImageAlphaInfo.none.rawValue)!
    ctx.setFillColor(gray: 1, alpha: 1); ctx.fill(CGRect(x: 0, y: 0, width: W, height: H))
    ctx.scaleBy(x: S, y: S); ctx.translateBy(x: -box.origin.x, y: -box.origin.y)
    page.draw(with: .mediaBox, to: ctx)
    let buf = ctx.data!.assumingMemoryBound(to: UInt8.self)
    // 行 y 从顶部起算（CGContext 缓冲区第 0 行即页面顶部）
    let cx = W / 2, g = Int(4 * S)
    var rowDark = [Bool](repeating: false, count: H)
    var gutDark = [Bool](repeating: false, count: H)
    var colMinL = W, colMaxL = 0, colMinR = W, colMaxR = 0
    for y in 0..<H {
        let row = buf + y * W
        let xa = Int(0.065 * Double(W)), xb = Int(0.935 * Double(W))   // 只看正文区，跳过页边竖排水印
        for x in xa..<xb where row[x] < 200 {
            rowDark[y] = true
            if x >= cx - g && x <= cx + g { gutDark[y] = true }
            if x < cx { colMinL = min(colMinL, x); colMaxL = max(colMaxL, x) }
            else { colMinR = min(colMinR, x); colMaxR = max(colMaxR, x) }
        }
    }
    let dark = rowDark.filter { $0 }.count
    gutRatio.append(dark > 0 ? Double(gutDark.filter { $0 }.count) / Double(dark) : 0)
    inkTop.append(CGFloat(rowDark.firstIndex(of: true) ?? 0) / S)
    inkBot.append(CGFloat(rowDark.lastIndex(of: true) ?? (H - 1)) / S)
    var ink: [Int] = []
    for yy in 0..<(H / Int(S)) {
        var m = 0
        for sub in 0..<Int(S) {
            let row = buf + (yy * Int(S) + sub) * W
            for x in stride(from: 0, to: W, by: 1) where row[x] < 200 { m |= 1 << min(31, x * 32 / W) }
        }
        ink.append(m)
    }
    // 按空白行切块，再判断块是否跨过中缝
    var blocks: [(Int, Int, Bool)] = []
    var y = 0; let gapMin = Int(5 * S)
    while y < H {
        if !rowDark[y] { y += 1; continue }
        var y1 = y, blank = 0, gut = 0
        var k = y
        while k < H {
            if rowDark[k] { blank = 0; y1 = k; if gutDark[k] { gut += 1 } } else { blank += 1; if blank >= gapMin { break } }
            k += 1
        }
        let h = y1 - y + 1
        blocks.append((y, y1, Double(gut) / Double(h) > 0.03))
        y = k
    }
    // 合并相邻同类块：连续的双栏块必须合成一个带，保证“先读完左栏再读右栏”
    var bands: [[String: Any]] = []
    for b in blocks {
        if let last = bands.last, (last["full"] as! Bool) == b.2 {
            bands[bands.count - 1]["y1"] = CGFloat(b.1) / S
        } else {
            bands.append(["y0": CGFloat(b.0) / S, "y1": CGFloat(b.1) / S, "full": b.2])
        }
    }
    pages.append(["w": box.width, "h": box.height, "bands": bands,
                  "xL": [CGFloat(colMinL) / S, CGFloat(colMaxL) / S],
                  "xR": [CGFloat(colMinR) / S, CGFloat(colMaxR) / S], "ink": ink])
}
// 单栏判定：一半以上页面的正文横跨中缝
let single = gutRatio.filter { $0 > 0.45 }.count * 2 > gutRatio.count
if single {
    for i in 0..<pages.count { pages[i]["bands"] = [["y0": inkTop[i], "y1": inkBot[i], "full": true]] }
}
let out: [String: Any] = ["pages": pages, "single": single]
try! JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted]).write(to: URL(fileURLWithPath: args[2]))
print("页数 \(pages.count)，" + (single ? "单栏：按阅读顺序重排" : "双栏"))
