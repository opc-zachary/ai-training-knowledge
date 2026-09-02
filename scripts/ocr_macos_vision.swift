#!/usr/bin/env swift

import AppKit
import Foundation
import Vision

struct OCRResult: Codable {
    let path: String
    let status: String
    let languages: [String]
    let text: String
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.withoutEscapingSlashes]

let preferredLanguages = ["zh-Hant", "zh-Hans", "en-US"]
let supportedLanguages: [String]
do {
    let supported = try VNRecognizeTextRequest.supportedRecognitionLanguages(
        for: .accurate,
        revision: VNRecognizeTextRequest.currentRevision
    )
    supportedLanguages = preferredLanguages.filter { supported.contains($0) }
} catch {
    supportedLanguages = []
}

for path in CommandLine.arguments.dropFirst() {
    var status = "unavailable"
    var recognizedText = ""
    if let image = NSImage(contentsOfFile: path) {
        var proposedRect = NSRect(origin: .zero, size: image.size)
        if let cgImage = image.cgImage(forProposedRect: &proposedRect, context: nil, hints: nil) {
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true
            if !supportedLanguages.isEmpty {
                request.recognitionLanguages = supportedLanguages
            }
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            do {
                try handler.perform([request])
                let observations = request.results ?? []
                let lines = observations.compactMap { $0.topCandidates(1).first?.string }
                recognizedText = lines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
                status = recognizedText.isEmpty ? "no_text_detected" : "recognized"
            } catch {
                status = "unavailable"
            }
        }
    }
    let result = OCRResult(
        path: path,
        status: status,
        languages: supportedLanguages,
        text: recognizedText
    )
    if let data = try? encoder.encode(result), let line = String(data: data, encoding: .utf8) {
        print(line)
    }
}
