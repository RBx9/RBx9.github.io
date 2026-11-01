import Foundation

/// Background URLSession retries network interruptions without throwing away
/// the staged file. GitHub's release API has no byte-range resume endpoint:
/// an interrupted POST may have to re-transfer the file from byte 0.
final class RBx9UploadTransport: NSObject, URLSessionDataDelegate, URLSessionTaskDelegate {
    static let shared = RBx9UploadTransport()
    typealias ProgressHandler = (Int64,Int64,Double?) -> Void

    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.background(
            withIdentifier:"com.rbx9.sourcemanager.release-asset-upload"
        )
        config.isDiscretionary = false
        config.sessionSendsLaunchEvents = true
        config.timeoutIntervalForResource = 7 * 24 * 60 * 60
        config.waitsForConnectivity = true
        return URLSession(configuration:config,delegate:self,delegateQueue:nil)
    }()
    private let mutex = NSLock()
    private var continuations:[Int:CheckedContinuation<(Data,URLResponse),Error>] = [:]
    private var buffers:[Int:Data] = [:]
    private var progressCallbacks:[Int:ProgressHandler] = [:]
    private var samples:[Int:(bytes:Int64,time:Date,rate:Double)] = [:]

    private override init() { super.init() }

    func upload(request:URLRequest,fromFile file:URL,
                onProgress:@escaping ProgressHandler) async throws -> (Data,URLResponse) {
        try await withCheckedThrowingContinuation { continuation in
            let task = session.uploadTask(with:request,fromFile:file)
            mutex.lock()
            continuations[task.taskIdentifier] = continuation
            buffers[task.taskIdentifier] = Data()
            progressCallbacks[task.taskIdentifier] = onProgress
            samples[task.taskIdentifier] = (0,Date(),0)
            mutex.unlock()
            task.resume()
        }
    }

    func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive data:Data) {
        mutex.lock()
        buffers[dataTask.taskIdentifier,default:Data()].append(data)
        mutex.unlock()
    }

    func urlSession(_ session:URLSession,task:URLSessionTask,
                    didSendBodyData bytesSent:Int64,
                    totalBytesSent:Int64,totalBytesExpectedToSend:Int64) {
        mutex.lock()
        let previous = samples[task.taskIdentifier] ?? (0,Date(),0.0)
        let elapsed = Date().timeIntervalSince(previous.time)
        let observedRate = elapsed > 0.35 ?
            Double(totalBytesSent - previous.bytes) / elapsed : previous.rate
        let smoothedRate = previous.rate <= 0 ? max(0,observedRate) :
            (0.65 * previous.rate + 0.35 * max(0,observedRate))
        if elapsed > 0.35 {
            samples[task.taskIdentifier] = (totalBytesSent,Date(),smoothedRate)
        }
        let callback = progressCallbacks[task.taskIdentifier]
        mutex.unlock()
        let remaining = max(0,totalBytesExpectedToSend-totalBytesSent)
        let eta:Double? = smoothedRate > 1024 ? Double(remaining)/smoothedRate : nil
        callback?(totalBytesSent,totalBytesExpectedToSend,eta)
    }

    func urlSession(_ session:URLSession,task:URLSessionTask,
                    didCompleteWithError error:Error?) {
        mutex.lock()
        let id=task.taskIdentifier
        let completion=continuations.removeValue(forKey:id)
        let payload=buffers.removeValue(forKey:id) ?? Data()
        progressCallbacks.removeValue(forKey:id)
        samples.removeValue(forKey:id)
        mutex.unlock()
        guard let completion else { return }
        if let error { completion.resume(throwing:error) }
        else if let response=task.response { completion.resume(returning:(payload,response)) }
        else { completion.resume(throwing:URLError(.badServerResponse)) }
    }
}


/// Metadata is kept in Application Support, not temporary storage, so that
/// relaunching after an interrupted transfer does not lose the upload queue.
struct RBx9PendingPublication: Codable {
    var stagedPath:String
    var filename:String
    var sileo:Bool
    var releaseID:Int?
    var completedAssetURL:String?
    var tag:String?
}

enum RBx9PendingUploadStore {
    static var directory:URL {
        let root = FileManager.default.urls(for:.applicationSupportDirectory,
            in:.userDomainMask)[0].appendingPathComponent("RBx9Uploads",isDirectory:true)
        try? FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
        return root
    }
    private static var record:URL { directory.appendingPathComponent("pending.json") }
    static func load() -> RBx9PendingPublication? {
        guard let data = try? Data(contentsOf:record) else { return nil }
        return try? JSONDecoder().decode(RBx9PendingPublication.self,from:data)
    }
    static func save(_ value:RBx9PendingPublication) throws {
        let data=try JSONEncoder().encode(value)
        try data.write(to:record,options:.atomic)
    }
    static func clear() { try? FileManager.default.removeItem(at:record) }
}


struct RBx9PendingDylib: Codable {
    var path:String
    var name:String
}
struct RBx9PendingInjection: Codable {
    var ipaPath:String
    var ipaName:String
    var outputName:String
    var libraries:[RBx9PendingDylib]
    var tag:String
    var releaseID:Int?
}
enum RBx9PendingInjectionStore {
    private static var file:URL {
        RBx9PendingUploadStore.directory.appendingPathComponent("pending-injection.json")
    }
    static func load() -> RBx9PendingInjection? {
        guard let data=try? Data(contentsOf:file) else { return nil }
        return try? JSONDecoder().decode(RBx9PendingInjection.self,from:data)
    }
    static func save(_ value:RBx9PendingInjection) throws {
        try JSONEncoder().encode(value).write(to:file,options:.atomic)
    }
    static func clear() { try? FileManager.default.removeItem(at:file) }
}
