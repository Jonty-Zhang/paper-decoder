import PDFKit
let a = CommandLine.arguments
let doc = PDFDocument(url: URL(fileURLWithPath: a[1]))!
for q in a.dropFirst(2) {
    var pages: [Int] = []
    for i in 0..<doc.pageCount { if let s = doc.page(at: i)?.string, s.contains(q) { pages.append(i + 1) } }
    print(q, pages)
}
