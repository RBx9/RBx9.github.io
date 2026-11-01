import AppKit

let folder = "source-manager/App/Assets.xcassets/AppIcon.appiconset"
try FileManager.default.createDirectory(atPath:folder, withIntermediateDirectories:true)
let size = 1024
let image = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:size,pixelsHigh:size,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep:image)
NSGraphicsContext.current?.imageInterpolation = .high

let full = NSRect(x:0,y:0,width:size,height:size)
NSColor(calibratedRed:0.025,green:0.047,blue:0.10,alpha:1).setFill()
full.fill()

let bg = NSBezierPath(roundedRect:full.insetBy(dx:10,dy:10),xRadius:220,yRadius:220)
NSGradient(starting:NSColor(calibratedRed:0.01,green:0.20,blue:0.39,alpha:1),ending:NSColor(calibratedRed:0.016,green:0.035,blue:0.12,alpha:1))!.draw(in:bg,angle:135)

let glow = NSBezierPath(ovalIn:NSRect(x:120,y:360,width:780,height:780))
NSColor(calibratedRed:0.0,green:0.78,blue:1.0,alpha:0.13).setFill()
glow.fill()

for (i,w) in [(0,580.0),(1,520.0),(2,460.0)] {
    let x = (1024-w)/2 + Double(i)*16
    let y = 450.0 + Double(i)*50
    let shape = NSBezierPath(roundedRect:NSRect(x:x,y:y,width:w,height:225),xRadius:42,yRadius:42)
    NSColor(calibratedRed:0.28,green:0.91,blue:1.0,alpha:i == 2 ? 0.94 : 0.23).setFill()
    shape.fill()
}
let text = "RBx9" as NSString
let font = NSFont.systemFont(ofSize:190,weight:.black)
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.55)
shadow.shadowBlurRadius = 24
shadow.shadowOffset = NSSize(width:0,height:-8)
let attrs:[NSAttributedString.Key:Any] = [
    .font:font,.foregroundColor:NSColor.white,.shadow:shadow
]
let textSize = text.size(withAttributes:attrs)
text.draw(at:NSPoint(x:(1024-textSize.width)/2,y:205),withAttributes:attrs)
let small = "SOURCE MANAGER" as NSString
let smallAttrs:[NSAttributedString.Key:Any] = [
    .font:NSFont.systemFont(ofSize:42,weight:.semibold),
    .foregroundColor:NSColor(calibratedRed:0.55,green:0.91,blue:1,alpha:1),
    .kern:7.0
]
let smallSize=small.size(withAttributes:smallAttrs)
small.draw(at:NSPoint(x:(1024-smallSize.width)/2,y:142),withAttributes:smallAttrs)

NSGraphicsContext.current?.flushGraphics()
NSGraphicsContext.restoreGraphicsState()
let data=image.representation(using:.png,properties:[:])!
try data.write(to:URL(fileURLWithPath:folder+"/AppIcon.png"))
print("Created",folder+"/AppIcon.png",data.count)
