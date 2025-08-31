import Foundation

enum TimerState: String, CaseIterable, Codable {
    case idle = "idle"
    case running = "running"
    case paused = "paused"
    case expired = "expired"
    
    var isCompleted: Bool {
        return self == .expired
    }
}

struct TimerItem: Identifiable, Codable {
    let id = UUID()
    var name: String
    var durationMinutes: Int
    var category: TimerCategory
    var state: TimerState = .idle
    var startTime: Date?
    var pausedTime: Date?
    var totalPausedDuration: TimeInterval = 0
    
    // Backward compatibility computed properties
    var isRunning: Bool {
        return state == .running
    }
    
    var isPaused: Bool {
        return state == .paused
    }
    
    var isCompleted: Bool {
        return state.isCompleted
    }
    
    var isIdle: Bool {
        return state == .idle
    }
    
    init(name: String, durationMinutes: Int, category: TimerCategory) {
        self.name = name
        self.durationMinutes = durationMinutes
        self.category = category
    }
    
    var totalDuration: TimeInterval {
        return TimeInterval(durationMinutes * 60)
    }
    
    var remainingTime: TimeInterval {
        guard durationSeconds > 0 else { return 0 }
        
        switch state {
        case .idle:
            return totalDuration
        case .running:
            guard let startTime = startTime else { return totalDuration }
            let elapsed = Date().timeIntervalSince(startTime) - totalPausedDuration
            return max(0, totalDuration - elapsed)
        case .paused:
            guard let startTime = startTime else { return totalDuration }
            let elapsed = (pausedTime?.timeIntervalSince(startTime) ?? 0) - totalPausedDuration
            return max(0, totalDuration - elapsed)
        case .expired:
            return 0
        }
    }
    
    var progress: Double {
        guard totalDuration > 0 else { return 0 }
        return 1.0 - (remainingTime / totalDuration)
    }
    
    private var durationSeconds: Int {
        return durationMinutes * 60
    }
    
    mutating func start() {
        state = .running
        startTime = Date()
        pausedTime = nil
    }
    
    mutating func pause() {
        guard state == .running else { return }
        state = .paused
        pausedTime = Date()
    }
    
    mutating func resume() {
        guard state == .paused else { return }
        state = .running
        
        if let pausedTime = pausedTime, let startTime = startTime {
            totalPausedDuration += Date().timeIntervalSince(pausedTime)
        }
        
        self.pausedTime = nil
    }
    
    mutating func reset() {
        state = .idle
        startTime = nil
        pausedTime = nil
        totalPausedDuration = 0
    }
    
    mutating func complete() {
        state = .expired
    }
    
    mutating func stop() {
        state = .idle
        startTime = nil
        pausedTime = nil
        totalPausedDuration = 0
    }
    
    mutating func snooze() {
        // Add 5 minutes to the timer
        durationMinutes += 5
        state = .running
        startTime = Date()
        pausedTime = nil
    }
}
