// 按行提取 PDF 文字及其位置（y 从页面顶部起算）
// 用法: swift lines.swift in.pdf out.json
import Foundation; import PDFKit
let a = CommandLine.arguments; let doc = PDFDocument(url: URL(fileURLWithPath: a[1]))!
var pages: [[[String: Any]]] = []
for pi in 0..<doc.pageCount {
    let p = doc.page(at: pi)!; let box = p.bounds(for: .mediaBox)
    var out: [[String: Any]] = []
    if let sel = p.selection(for: box) {
        for l in sel.selectionsByLine() {
            let r = l.bounds(for: p); let t = (l.string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if t.isEmpty || r.width < 1 { continue }
            out.append(["x0": r.minX, "x1": r.maxX, "y0": box.height - r.maxY, "y1": box.height - r.minY, "t": t])
        }
    }
    pages.append(out)
}
try! JSONSerialization.data(withJSONObject: pages).write(to: URL(fileURLWithPath: a[2]))
print("页数", pages.count, "总行数", pages.map { $0.count }.reduce(0, +))
