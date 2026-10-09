// verbalis-audiotap – records the system audio on macOS 14.2+ for Verbalis.
//
// macOS has no loopback like Windows. Since macOS 14.2 Core Audio offers "process taps":
// a tap receives the audio all programs play (here: a global stereo tap, like Windows
// loopback), the user keeps hearing everything. The tap is read through a private
// aggregate device.
//
// Protocol with Verbalis (src/verbalis/audio/mac_tap.py):
//   stderr, first line: {"samplerate": 48000, "channels": 2}   or   {"error": "…"}
//   stdout:             mono samples, 32-bit float, native byte order, continuously
// Stops on SIGTERM/SIGINT (cleans up the tap and the aggregate device) or when stdout closes.
//
// Build (done by the GitHub Actions on a Mac):
//   swiftc -O -target arm64-apple-macos14.2 -o tools/macos/build/verbalis-audiotap tools/macos/audiotap.swift
//
// macOS asks once for permission ("Audioaufnahme"); the text comes from
// NSAudioCaptureUsageDescription in Verbalis.app's Info.plist. Without permission the
// tap delivers silence – Verbalis then shows its warning about a silent track.

import AudioToolbox
import CoreAudio
import Foundation

let version = "1"

func writeErr(_ text: String) {
    FileHandle.standardError.write((text + "\n").data(using: .utf8)!)
}

func fail(_ message: String, _ status: OSStatus = noErr) -> Never {
    let detail = status == noErr ? message : "\(message) (OSStatus \(status))"
    let escaped = detail.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"")
    writeErr("{\"error\": \"\(escaped)\"}")
    exit(1)
}

func address(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector,
                               mScope: kAudioObjectPropertyScopeGlobal,
                               mElement: kAudioObjectPropertyElementMain)
}

// ---------------------------------------------------------------- arguments

if CommandLine.arguments.contains("--version") {
    print("verbalis-audiotap \(version)")
    exit(0)
}

// ---------------------------------------------------------------- default output device (clock source)

var outputID = AudioObjectID(kAudioObjectUnknown)
do {
    var addr = address(kAudioHardwarePropertyDefaultOutputDevice)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    let status = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &outputID)
    if status != noErr || outputID == kAudioObjectUnknown { fail("Kein Ausgabegerät gefunden", status) }
}

var outputUID: String = ""
do {
    var addr = address(kAudioDevicePropertyDeviceUID)
    var uid: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    let status = AudioObjectGetPropertyData(outputID, &addr, 0, nil, &size, &uid)
    guard status == noErr, let value = uid else { fail("Ausgabegerät ohne Kennung", status) }
    outputUID = value.takeRetainedValue() as String
}

// ---------------------------------------------------------------- the tap

let tapDescription = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
let tapUUID = UUID()
tapDescription.uuid = tapUUID
tapDescription.name = "Verbalis"
tapDescription.isPrivate = true
tapDescription.muteBehavior = .unmuted        // the user keeps hearing the call

var tapID = AudioObjectID(kAudioObjectUnknown)
do {
    let status = AudioHardwareCreateProcessTap(tapDescription, &tapID)
    if status != noErr { fail("Systemton-Tap konnte nicht erstellt werden", status) }
}

var format = AudioStreamBasicDescription()
do {
    var addr = address(kAudioTapPropertyFormat)
    var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
    let status = AudioObjectGetPropertyData(tapID, &addr, 0, nil, &size, &format)
    if status != noErr { fail("Format des Systemtons unbekannt", status) }
}
let isFloat = format.mFormatID == kAudioFormatLinearPCM
    && (format.mFormatFlags & kAudioFormatFlagIsFloat) != 0 && format.mBitsPerChannel == 32
if !isFloat { fail("Unerwartetes Audioformat (\(format.mFormatID), \(format.mBitsPerChannel) Bit)") }

// ---------------------------------------------------------------- private aggregate device with the tap

let aggregateDescription: [String: Any] = [
    kAudioAggregateDeviceNameKey: "Verbalis Systemton",
    kAudioAggregateDeviceUIDKey: UUID().uuidString,
    kAudioAggregateDeviceMainSubDeviceKey: outputUID,
    kAudioAggregateDeviceIsPrivateKey: true,
    kAudioAggregateDeviceIsStackedKey: false,
    kAudioAggregateDeviceTapAutoStartKey: true,
    kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
    kAudioAggregateDeviceTapListKey: [[kAudioSubTapDriftCompensationKey: true,
                                       kAudioSubTapUIDKey: tapUUID.uuidString]],
]

var aggregateID = AudioObjectID(kAudioObjectUnknown)
do {
    let status = AudioHardwareCreateAggregateDevice(aggregateDescription as CFDictionary, &aggregateID)
    if status != noErr {
        AudioHardwareDestroyProcessTap(tapID)
        fail("Aggregat-Gerät konnte nicht erstellt werden", status)
    }
}

// ---------------------------------------------------------------- reading: downmix to mono, write to stdout

let output = FileHandle.standardOutput
let ioQueue = DispatchQueue(label: "ch.frehner.verbalis.audiotap")
var procID: AudioDeviceIOProcID?

let ioBlock: AudioDeviceIOBlock = { _, inputData, _, _, _ in
    let buffers = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: inputData))
    guard let first = buffers.first, first.mDataByteSize > 0 else { return }
    let firstChannels = max(Int(first.mNumberChannels), 1)
    let frames = Int(first.mDataByteSize) / (MemoryLayout<Float32>.size * firstChannels)
    var mono = [Float32](repeating: 0, count: frames)
    var channels = 0
    for buffer in buffers {             // works for interleaved (1 buffer) and planar (1 per channel)
        guard let data = buffer.mData?.assumingMemoryBound(to: Float32.self) else { continue }
        let n = max(Int(buffer.mNumberChannels), 1)
        for frame in 0..<frames {
            var sum: Float32 = 0
            for channel in 0..<n { sum += data[frame * n + channel] }
            mono[frame] += sum
        }
        channels += n
    }
    if channels > 1 {
        let scale = 1 / Float32(channels)
        for i in 0..<frames { mono[i] *= scale }
    }
    mono.withUnsafeBufferPointer { output.write(Data(buffer: $0)) }   // SIGPIPE ends us if Verbalis is gone
}

do {
    var status = AudioDeviceCreateIOProcIDWithBlock(&procID, aggregateID, ioQueue, ioBlock)
    if status != noErr { fail("Lesen des Systemtons nicht möglich", status) }
    status = AudioDeviceStart(aggregateID, procID)
    if status != noErr { fail("Systemton-Aufnahme konnte nicht starten", status) }
}

writeErr("{\"samplerate\": \(Int(format.mSampleRate)), \"channels\": \(format.mChannelsPerFrame)}")

// ---------------------------------------------------------------- clean shutdown

func cleanup() {
    if let proc = procID {
        AudioDeviceStop(aggregateID, proc)
        AudioDeviceDestroyIOProcID(aggregateID, proc)
    }
    AudioHardwareDestroyAggregateDevice(aggregateID)
    AudioHardwareDestroyProcessTap(tapID)
}

var signalSources: [DispatchSourceSignal] = []
for sig in [SIGTERM, SIGINT] {
    signal(sig, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler {
        cleanup()
        exit(0)
    }
    source.resume()
    signalSources.append(source)
}

dispatchMain()
