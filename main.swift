import AppKit
import ImageIO
import UniformTypeIdentifiers

// Artwork.swift is generated from the pinned, locally vendored SVGs.
struct EmbeddedCursor {
    let name: String
    let identifiers: [String]
    let x: Double
    let y: Double
    let pngs: [String]
}

struct PreparedCursor {
    let identifiers: [String]
    let size: CGSize
    let hotspot: CGPoint
    let images: [CGImage]
}

struct Failure: Error, CustomStringConvertible {
    let description: String
    init(_ message: String) { description = message }
}

func require(_ condition: Bool, _ message: String) throws {
    guard condition else { throw Failure(message) }
}

func checked(_ error: CGError, _ operation: String) throws {
    try require(error == .success, "\(operation) failed (macOS error \(error.rawValue)).")
}

func prepare(_ artwork: [EmbeddedCursor], pointSize: Int) throws -> [PreparedCursor] {
    try require((16...32).contains(pointSize), "Size must be a whole number from 16 to 32 points.")
    try require((1...32).contains(artwork.count), "Unexpected cursor count.")
    var identifiers = Set<String>()
    return try artwork.map { cursor in
        try require(cursor.x.isFinite && cursor.y.isFinite &&
                    (0..<32).contains(cursor.x) && (0..<32).contains(cursor.y),
                    "Invalid hotspot: \(cursor.name).")
        try require((1...8).contains(cursor.identifiers.count), "Invalid identifier count.")
        for identifier in cursor.identifiers {
            try require(identifier.utf8.count <= 96 &&
                        identifier.hasPrefix("com.apple.") &&
                        identifier.utf8.allSatisfy { $0 == 45 || $0 == 46 || (48...57).contains($0) ||
                            (65...90).contains($0) || (97...122).contains($0) } &&
                        identifiers.insert(identifier).inserted,
                        "Invalid or duplicate cursor identifier.")
        }
        try require(cursor.pngs.count == 2, "Missing 1x/2x image: \(cursor.name).")
        let images = try cursor.pngs.enumerated().map { index, encoded -> CGImage in
            // Bound input before decoding; inspect dimensions before allocating pixels.
            try require(encoded.utf8.count <= 131_072, "Image is too large.")
            guard let data = Data(base64Encoded: encoded),
                  let source = CGImageSourceCreateWithData(data as CFData, nil) else {
                throw Failure("Invalid embedded PNG: \(cursor.name).")
            }
            let pixels = 32 * (index + 1)
            let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
            try require(CGImageSourceGetType(source) as String? == UTType.png.identifier &&
                        CGImageSourceGetCount(source) == 1 &&
                        (properties?[kCGImagePropertyPixelWidth] as? Int) == pixels &&
                        (properties?[kCGImagePropertyPixelHeight] as? Int) == pixels,
                        "Unexpected PNG format or dimensions: \(cursor.name).")
            guard let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
                throw Failure("Cannot decode PNG: \(cursor.name).")
            }
            try require(image.bitsPerComponent == 8 && image.bitsPerPixel == 32,
                        "Expected 8-bit RGBA artwork: \(cursor.name).")
            let targetPixels = pointSize * (index + 1)
            if targetPixels == pixels { return image }
            guard let space = CGColorSpace(name: CGColorSpace.sRGB),
                  let context = CGContext(data: nil, width: targetPixels, height: targetPixels,
                    bitsPerComponent: 8, bytesPerRow: targetPixels * 4, space: space,
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
                throw Failure("Cannot allocate resized cursor: \(cursor.name).")
            }
            context.interpolationQuality = .high
            context.draw(image, in: CGRect(x: 0, y: 0, width: CGFloat(targetPixels), height: CGFloat(targetPixels)))
            guard let resized = context.makeImage() else { throw Failure("Cannot resize cursor.") }
            return resized
        }
        return PreparedCursor(identifiers: cursor.identifiers,
                              size: CGSize(width: CGFloat(pointSize), height: CGFloat(pointSize)),
                              hotspot: CGPoint(x: cursor.x * Double(pointSize) / 32,
                                               y: cursor.y * Double(pointSize) / 32), images: images)
    }
}

func refresh(_ connection: CGSConnectionID) throws {
    try checked(CGSSetSystemDefinedCursor(connection, 0), "Select arrow")
    var scale: Float = 1
    try checked(CGSGetCursorScale(connection, &scale), "Read cursor scale")
    try require(scale.isFinite && scale > 0 && scale <= 32, "Unexpected system cursor scale.")
    // Invalidate the compositor's cached cursor, preserving the user's size setting.
    try checked(CGSSetCursorScale(connection, scale + 0.01), "Refresh cursor")
    try checked(CGSSetCursorScale(connection, scale), "Restore cursor scale")
}

func reset(_ connection: CGSConnectionID) throws {
    try checked(CoreCursorUnregisterAll(connection), "Unregister custom cursors")
    // Ask macOS to recreate its built-in cursor cache; a few IDs are unused.
    for identifier: Int32 in 0...43 { _ = CoreCursorSet(connection, identifier) }
    CGSSetDockCursorOverride(connection, false)
    try refresh(connection)
}

func apply(_ cursors: [PreparedCursor], _ connection: CGSConnectionID) throws {
    // All artwork has been decoded and validated before the first global mutation.
    // Clear any previous broader theme before installing the arrow, hands and I-beam.
    try reset(connection)
    do {
        for cursor in cursors {
            for identifier in cursor.identifiers {
                var name = Array(identifier.utf8CString)
                var seed: Int32 = 0
                try name.withUnsafeMutableBufferPointer { buffer in
                    try checked(CGSRegisterCursorWithImages(connection, buffer.baseAddress,
                        true, true, cursor.size, cursor.hotspot,
                        1, 0, cursor.images as CFArray, &seed), "Register \(identifier)")
                    try checked(CGSSetRegisteredCursor(connection, buffer.baseAddress, &seed),
                                "Activate \(identifier)")
                }
            }
        }
        CGSSetDockCursorOverride(connection, true)
        try refresh(connection)
    } catch {
        // An unsupported private API must not leave a half-applied theme silently.
        do { try reset(connection) }
        catch { FileHandle.standardError.write(Data("Automatic reset also failed: \(error)\n".utf8)) }
        throw error
    }
}

let usage = """
Usage: apple-cursor check|apply [--size POINTS] | reset
  check  Validate every embedded image without changing your cursor.
  apply  Restore defaults, apply the arrow, hands and text I-beam, then exit.
  reset  Ask macOS to restore its built-in cursors, then exit.
Size is the cursor canvas width, 16–32 points; default 24 (previous size: 32).
No background process, network access, or elevated privileges.
Optional login startup: sh login.sh [--size POINTS]; remove with sh login.sh --remove.
"""

do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    if arguments.isEmpty || arguments == ["--help"] || arguments == ["-h"] {
        print(usage)
    } else {
        let command = arguments[0]
        try require(["check", "apply", "reset"].contains(command), usage)
        var pointSize = 24
        if command != "reset" && arguments.count == 3 && arguments[1] == "--size" {
            guard let value = Int(arguments[2]) else { throw Failure("Size must be a whole number from 16 to 32 points.") }
            pointSize = value
        } else {
            try require(arguments.count == 1, usage)
        }
        try require((16...32).contains(pointSize), "Size must be a whole number from 16 to 32 points.")
        if command == "check" {
            let cursors = try prepare(embeddedArtwork, pointSize: pointSize)
            print("Validated \(cursors.count) static cursors, \(cursors.reduce(0) { $0 + $1.identifiers.count }) identifiers, 1x/2x images at \(pointSize) points. No cursor changes.")
        } else {
            try require(getuid() != 0 && geteuid() != 0, "Run as your normal desktop user, never with sudo.")
            let major = ProcessInfo.processInfo.operatingSystemVersion.majorVersion
            try require((26...27).contains(major), "This private-API build supports macOS 26–27 only.")
            let cursors = command == "apply" ? try prepare(embeddedArtwork, pointSize: pointSize) : []
            _ = NSApplication.shared.setActivationPolicy(.prohibited)
            let connection = CGSMainConnectionID()
            try require(connection != 0, "No WindowServer connection. Run inside your logged-in graphical session.")
            if command == "apply" {
                try apply(cursors, connection)
                print("Applied the arrow, hand and text I-beam cursors at \(pointSize) points; requested macOS defaults for all others.")
            } else {
                try reset(connection)
                print("Requested the macOS default cursors. If a cursor stays cached, log out and back in.")
            }
        }
    }
} catch {
    FileHandle.standardError.write(Data("apple-cursor: \(error)\n".utf8))
    exit(1)
}
