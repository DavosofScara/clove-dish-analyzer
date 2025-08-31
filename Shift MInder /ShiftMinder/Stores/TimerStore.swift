import Foundation
import SwiftUI
import AudioToolbox
import AVFoundation

class TimerStore: ObservableObject {
    @Published var timers: [TimerItem] = []
    @Published var appSettings: AppSettings = AppSettings.default
    
    private let persistence = Persistence()
    private let notificationScheduler = NotificationScheduler()
    private let haptics = Haptics()
    private var updateTimer: Timer?
    
    init() {
        loadTimers()
        loadSettings()
        startUpdateTimer()
        setupAudioSession()
    }
    
    deinit {
        updateTimer?.invalidate()
    }
    
    // MARK: - Timer Management
    
    func addTimer(_ timer: TimerItem) {
        timers.append(timer)
        saveTimers()
        scheduleNotification(for: timer)
    }
    
    func updateTimer(_ timer: TimerItem) {
        if let index = timers.firstIndex(where: { $0.id == timer.id }) {
            timers[index] = timer
            saveTimers()
            scheduleNotification(for: timer)
        }
    }
    
    func deleteTimer(_ timer: TimerItem) {
        timers.removeAll { $0.id == timer.id }
        saveTimers()
        notificationScheduler.cancelNotification(for: timer)
    }
    
    func resetTimer(_ timer: TimerItem) {
        if let index = timers.firstIndex(where: { $0.id == timer.id }) {
            timers[index].reset()
            saveTimers()
            notificationScheduler.cancelNotification(for: timer)
            clearAppBadge()
        }
    }
    
    func moveTimerToTop(_ timer: TimerItem) {
        if let index = timers.firstIndex(where: { $0.id == timer.id }) {
            let movedTimer = timers.remove(at: index)
            timers.insert(movedTimer, at: 0)
            saveTimers()
        }
    }
    
    // MARK: - Timer Actions
    
    func startTimer(_ timer: TimerItem) {
        if let index = timers.firstIndex(where: { $0.id == timer.id }) {
            timers[index].start()
            saveTimers()
            scheduleNotification(for: timers[index])
            
            if appSettings.hapticsEnabled {
                DispatchQueue.main.async { [weak self] in
                    self?.haptics.buttonPress()
                }
            }
        }
    }
    
    func pauseTimer(_ timer: TimerItem) {
        if let index = timers.firstIndex(where: { $0.id == timer.id }) {
            timers[index].pause()
            saveTimers()
            notificationScheduler.cancelNotification(for: timer)
            
            if appSettings.hapticsEnabled {
                DispatchQueue.main.async { [weak self] in
                    self?.haptics.buttonPress()
                }
            }
        }
    }
    
    func resumeTimer(_ timer: TimerItem) {
        if let index = timers.firstIndex(where: { $0.id == timer.id }) {
            timers[index].resume()
            saveTimers()
            scheduleNotification(for: timers[index])
            
            if appSettings.hapticsEnabled {
                DispatchQueue.main.async { [weak self] in
                    self?.haptics.buttonPress()
                }
            }
        }
    }
    
    func snoozeTimer(_ timer: TimerItem) {
        if let index = timers.firstIndex(where: { $0.id == timer.id }) {
            timers[index].snooze()
            saveTimers()
            scheduleSnoozeNotification(for: timers[index])
            
            if appSettings.hapticsEnabled {
                DispatchQueue.main.async { [weak self] in
                    self?.haptics.snooze()
                }
            }
        }
    }
    
    func stopTimer(_ timer: TimerItem) {
        if let index = timers.firstIndex(where: { $0.id == timer.id }) {
            timers[index].stop()
            saveTimers()
            notificationScheduler.cancelNotification(for: timer)
            
            if appSettings.hapticsEnabled {
                DispatchQueue.main.async { [weak self] in
                    self?.haptics.stop()
                }
            }
        }
    }
    
    // MARK: - Computed Properties
    
    var activeTimers: [TimerItem] {
        timers.filter { $0.state == .running || $0.state == .paused }
    }
    
    var completedTimers: [TimerItem] {
        timers.filter { $0.state.isCompleted }
    }
    
    var getCustomTimers: [TimerItem] {
        timers.filter { $0.category == .custom }
    }
    
    // MARK: - Settings Management
    
    func updateSettings(_ newSettings: AppSettings) {
        appSettings = newSettings
        saveSettings()
        DispatchQueue.main.async { [weak self] in
            self?.objectWillChange.send()
        }
    }
    
    func updateSettingsProperty<T>(_ keyPath: WritableKeyPath<AppSettings, T>, to value: T) {
        appSettings[keyPath: keyPath] = value
        saveSettings()
        DispatchQueue.main.async { [weak self] in
            self?.objectWillChange.send()
        }
    }
    
    func syncAppTheme(_ appTheme: AppTheme) {
        appTheme.updateThemeFromTimerStore(self)
    }
    
    // MARK: - Private Methods
    
    private func startUpdateTimer() {
        updateTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.updateTimers()
        }
    }
    
    private func updateTimers() {
        let timersCopy = timers
        var completedTimers: [TimerItem] = []
        
        for timer in timersCopy {
            if timer.remainingTime <= 0 && timer.isRunning {
                completedTimers.append(timer)
            }
        }
        
        for timer in completedTimers {
            if let index = timers.firstIndex(where: { $0.id == timer.id }) {
                timers[index].complete()
                saveTimers()
                
                // Play alarm sound immediately
                DispatchQueue.main.async { [weak self] in
                    self?.ensureAudioSessionActive()
                    AudioServicesPlaySystemSound(self?.appSettings.alarmSound.systemSoundId ?? 1005)
                }
                
                if appSettings.hapticsEnabled {
                    DispatchQueue.main.async { [weak self] in
                        self?.haptics.timerComplete()
                    }
                }
                
                DispatchQueue.main.async { [weak self] in
                    self?.objectWillChange.send()
                }
            }
        }
    }
    
    private func scheduleNotification(for timer: TimerItem) {
        notificationScheduler.scheduleTimerNotification(for: timer, alarmSound: appSettings.alarmSound)
    }
    
    private func scheduleSnoozeNotification(for timer: TimerItem) {
        notificationScheduler.scheduleSnoozeNotification(for: timer, alarmSound: appSettings.alarmSound)
    }
    
    private func setupAudioSession() {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.playback, mode: .default, options: [.defaultToSpeaker, .allowBluetooth])
            try audioSession.setActive(true)
        } catch {
            print("Failed to setup audio session: \(error)")
        }
    }
    
    private func ensureAudioSessionActive() {
        do {
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {
            print("Failed to activate audio session: \(error)")
        }
    }
    
    private func clearAppBadge() {
        DispatchQueue.main.async {
            UIApplication.shared.applicationIconBadgeNumber = 0
            UNUserNotificationCenter.current().removeAllDeliveredNotifications()
        }
    }
    
    // MARK: - Persistence
    
    private func loadTimers() {
        timers = persistence.loadTimers()
    }
    
    private func saveTimers() {
        persistence.saveTimers(timers)
    }
    
    private func loadSettings() {
        appSettings = persistence.loadSettings()
    }
    
    private func saveSettings() {
        persistence.saveSettings(appSettings)
    }
}
