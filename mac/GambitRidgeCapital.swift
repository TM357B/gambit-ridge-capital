// Gambit Ridge Capital — fenêtre native macOS (WKWebView, sans navigateur).
// Compile : swiftc -o GambitRidgeCapital GambitRidgeCapital.swift -framework Cocoa -framework WebKit -framework Speech -framework AVFoundation
//
// Voix : WKWebView n'implémente pas la reconnaissance vocale du web
// (SpeechRecognition). Le micro passe donc par le moteur natif de macOS
// (SFSpeechRecognizer + AVAudioEngine) et la synthèse par AVSpeechSynthesizer,
// exposés au terminal via le pont JS `window.webkit.messageHandlers.grcVoice`.
import Cocoa
import WebKit
import Speech
import AVFoundation

final class VoiceBridge: NSObject, WKScriptMessageHandler, AVSpeechSynthesizerDelegate {
    weak var webView: WKWebView?
    private let audioEngine = AVAudioEngine()
    private var recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var silenceTimer: Timer?
    private var lastText = ""
    private let synth = AVSpeechSynthesizer()

    override init() {
        super.init()
        synth.delegate = self
    }

    // MARK: JS -> natif
    func userContentController(_ uc: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let cmd = body["cmd"] as? String else { return }
        switch cmd {
        case "start": start(lang: body["lang"] as? String ?? "fr-FR")
        case "stop": stop(sendFinal: true)
        case "cancel": stop(sendFinal: false)
        case "speak": speak(body["text"] as? String ?? "", voiceIndex: body["voice"] as? Int ?? 0, rate: body["rate"] as? Double ?? 0.5)
        case "silence": synth.stopSpeaking(at: .immediate)
        case "voices": emit(["type": "voices", "voices": frenchVoices().map { ["name": $0.name, "quality": $0.quality.rawValue] }])
        default: break
        }
    }

    // MARK: natif -> JS
    private func emit(_ payload: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let json = String(data: data, encoding: .utf8) else { return }
        DispatchQueue.main.async {
            self.webView?.evaluateJavaScript("window.grcVoiceEvent && window.grcVoiceEvent(\(json))", completionHandler: nil)
        }
    }

    // MARK: reconnaissance
    private func start(lang: String) {
        if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
        SFSpeechRecognizer.requestAuthorization { status in
            DispatchQueue.main.async {
                guard status == .authorized else {
                    self.emit(["type": "error", "error": "Reconnaissance vocale refusée — Réglages Système > Confidentialité et sécurité > Reconnaissance vocale : autorise « Gambit Ridge Capital »."])
                    return
                }
                switch AVCaptureDevice.authorizationStatus(for: .audio) {
                case .authorized: self.beginRecognition(lang: lang)
                case .notDetermined:
                    AVCaptureDevice.requestAccess(for: .audio) { ok in
                        DispatchQueue.main.async {
                            if ok { self.beginRecognition(lang: lang) }
                            else { self.emit(["type": "error", "error": "Micro refusé — Réglages Système > Confidentialité et sécurité > Microphone : autorise « Gambit Ridge Capital »."]) }
                        }
                    }
                default:
                    self.emit(["type": "error", "error": "Micro refusé — Réglages Système > Confidentialité et sécurité > Microphone : autorise « Gambit Ridge Capital »."])
                }
            }
        }
    }

    private func beginRecognition(lang: String) {
        stop(sendFinal: false)
        recognizer = SFSpeechRecognizer(locale: Locale(identifier: lang))
        guard let recognizer = recognizer, recognizer.isAvailable else {
            emit(["type": "error", "error": "Dictée indisponible pour \(lang). Active la dictée : Réglages Système > Clavier > Dictée."])
            return
        }
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        if recognizer.supportsOnDeviceRecognition { req.requiresOnDeviceRecognition = true } // 100 % local quand possible
        request = req
        lastText = ""
        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.request?.append(buffer)
        }
        audioEngine.prepare()
        do { try audioEngine.start() } catch {
            emit(["type": "error", "error": "Impossible d'ouvrir le micro : \(error.localizedDescription)"])
            return
        }
        emit(["type": "state", "listening": true, "onDevice": req.requiresOnDeviceRecognition])
        task = recognizer.recognitionTask(with: req) { [weak self] result, error in
            guard let self = self else { return }
            if let result = result {
                self.lastText = result.bestTranscription.formattedString
                self.emit(["type": "partial", "text": self.lastText])
                self.armSilenceTimer()
                if result.isFinal { self.stop(sendFinal: true) }
            } else if error != nil, self.task != nil {
                self.stop(sendFinal: true)
            }
        }
        armSilenceTimer(initial: true)
    }

    private func armSilenceTimer(initial: Bool = false) {
        DispatchQueue.main.async {
            self.silenceTimer?.invalidate()
            // fin de phrase : 1,6 s sans nouveau mot (8 s si rien n'a encore été dit)
            self.silenceTimer = Timer.scheduledTimer(withTimeInterval: initial ? 8.0 : 1.6, repeats: false) { [weak self] _ in
                self?.stop(sendFinal: true)
            }
        }
    }

    private func stop(sendFinal: Bool) {
        silenceTimer?.invalidate(); silenceTimer = nil
        let wasRunning = task != nil || audioEngine.isRunning
        if audioEngine.isRunning {
            audioEngine.stop()
            audioEngine.inputNode.removeTap(onBus: 0)
        }
        request?.endAudio()
        task?.cancel()
        task = nil; request = nil
        if wasRunning {
            if sendFinal { emit(["type": "final", "text": lastText]) }
            emit(["type": "state", "listening": false])
        }
        lastText = ""
    }

    // MARK: synthèse
    private func frenchVoices() -> [AVSpeechSynthesisVoice] {
        // meilleures voix d'abord (premium > enhanced > default)
        AVSpeechSynthesisVoice.speechVoices()
            .filter { $0.language.hasPrefix("fr") }
            .sorted { $0.quality.rawValue > $1.quality.rawValue }
    }

    private func speak(_ text: String, voiceIndex: Int, rate: Double) {
        guard !text.isEmpty else { return }
        synth.stopSpeaking(at: .immediate)
        let u = AVSpeechUtterance(string: text)
        let voices = frenchVoices()
        if !voices.isEmpty { u.voice = voices[abs(voiceIndex) % voices.count] }
        u.rate = Float(rate)
        synth.speak(u)
    }

    func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        emit(["type": "speechEnd"])
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var horsLigne: Timer?
    let voice = VoiceBridge()
    let adresse = "http://127.0.0.1:8765"

    // Le terminal tourne sur le serveur ; le Mac l'atteint par le tunnel SSH (agent launchd
    // com.gambitridgecapital.tunnel, 127.0.0.1:8765). L'app ne lance JAMAIS de serveur local :
    // au démarrage du Mac, le tunnel n'était pas encore prêt, l'app lançait la vieille copie de
    // ~/gambit-ridge-capital, qui prenait le port du tunnel et affichait une version périmée (2026-10-23).
    func applicationDidFinishLaunching(_ notification: Notification) {
        relancerTunnelSiAbsent()
        attendreServeur(secondes: 60) { [weak self] ok in
            guard let self = self else { return }
            self.showWindow()
            ok ? self.chargerTerminal() : self.afficherHorsLigne()
        }
    }

    @discardableResult
    func shell(_ commande: String) -> Int32 {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/sh")
        task.arguments = ["-c", commande]
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        do { try task.run() } catch { return -1 }
        task.waitUntilExit()
        return task.terminationStatus
    }

    func relancerTunnelSiAbsent() {
        if shell("curl -s -m 2 -o /dev/null \(adresse)") != 0 {
            shell("launchctl kickstart -k gui/$(id -u)/com.gambitridgecapital.tunnel")
        }
    }

    func attendreServeur(secondes: Int, done: @escaping (Bool) -> Void) {
        DispatchQueue.global().async {
            let ok = self.shell("for i in $(seq 1 \(secondes)); do curl -s -m 2 -o /dev/null '\(self.adresse)' && exit 0; sleep 1; done; exit 1") == 0
            DispatchQueue.main.async { done(ok) }
        }
    }

    func chargerTerminal() {
        horsLigne?.invalidate(); horsLigne = nil
        var req = URLRequest(url: URL(string: adresse)!)
        req.cachePolicy = .reloadIgnoringLocalCacheData
        webView.load(req)
    }

    // Serveur injoignable : page explicite qui réessaie seule (toutes les 3 s), et relance du tunnel toutes les 30 s.
    func afficherHorsLigne() {
        let html = """
        <html><body style="background:#000;color:#e8e8e8;font-family:Menlo,monospace;padding:60px">
        <div style="color:#ff9900;font-weight:700;font-size:16px;letter-spacing:1px">GAMBIT RIDGE CAPITAL</div>
        <p style="margin-top:24px">Le serveur ne répond pas encore (tunnel SSH vers le serveur en cours de connexion).</p>
        <p style="color:#888">Nouvelle tentative automatique toutes les 3 secondes. Vérifie la connexion internet si cela dure.</p>
        <script>setInterval(function(){fetch('/api/market',{cache:'no-store'}).then(function(r){if(r.ok)location.replace('/')}).catch(function(){})},3000)</script>
        </body></html>
        """
        webView.loadHTMLString(html, baseURL: URL(string: adresse))
        horsLigne = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            DispatchQueue.global().async { self?.relancerTunnelSiAbsent() }
        }
    }

    func showWindow() {
        let cfg = WKWebViewConfiguration()
        cfg.userContentController.add(voice, name: "grcVoice")
        cfg.websiteDataStore = WKWebsiteDataStore.nonPersistent()
        webView = WKWebView(frame: .zero, configuration: cfg)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        voice.webView = webView
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        window.title = "Gambit Ridge Capital"
        window.minSize = NSSize(width: 1000, height: 640)
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    // liens target=_blank / window.open (rapport mensuel…) : ouverts dans le navigateur
    // par défaut, où « Imprimer > Enregistrer en PDF » est disponible
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    // getUserMedia éventuel depuis la page locale : accordé (le serveur n'écoute que 127.0.0.1)
    @available(macOS 12.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(origin.host == "127.0.0.1" ? .grant : .deny)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
