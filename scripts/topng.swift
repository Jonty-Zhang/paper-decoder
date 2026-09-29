import Foundation; import PDFKit; import AppKit
let a = CommandLine.arguments; let doc = PDFDocument(url: URL(fileURLWithPath: a[1]))!
let prefix = a[2]; let pages = a[3].split(separator: ",").map { Int($0)! }; let s: CGFloat = CGFloat(Double(a[4]) ?? 1.5)
for n in pages {
    let p = doc.page(at: n - 1)!; let r = p.bounds(for: .mediaBox)
    let img = NSImage(size: NSSize(width: r.width * s, height: r.height * s))
    img.lockFocus(); NSColor.white.set(); NSRect(x: 0, y: 0, width: r.width * s, height: r.height * s).fill()
    let ctx = NSGraphicsContext.current!.cgContext; ctx.scaleBy(x: s, y: s); p.draw(with: .mediaBox, to: ctx); img.unlockFocus()
    let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "\(prefix)\(n).png"))
}
print("done", doc.pageCount, "pages")
