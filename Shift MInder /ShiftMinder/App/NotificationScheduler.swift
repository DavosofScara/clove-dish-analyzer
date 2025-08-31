import Foundation
import UserNotifications

class NotificationScheduler {
    
    func scheduleTimerNotification(for timer: TimerItem, alarmSound: AlarmSound = .classic) {
        let content = UNMutableNotificationContent()
        content.title = "Timer Complete"
        content.body = "\(timer.name) has finished"
        content.sound = UNNotificationSound.defaultCritical
        content.badge = 1
        content.userInfo = [
            "timerId": timer.id.uuidString,
            "alarmSound": alarmSound.rawValue
        ]
        
        let trigger = UNTimeIntervalNotificationTrigger(
            timeInterval: timer.remainingTime,
            repeats: false
        )
        
        let request = UNNotificationRequest(
            identifier: timer.id.uuidString,
            content: content,
            trigger: trigger
        )
        
        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                print("Failed to schedule notification: \(error)")
            }
        }
    }
    
    func scheduleSnoozeNotification(for timer: TimerItem, alarmSound: AlarmSound = .classic) {
        let content = UNMutableNotificationContent()
        content.title = "Timer Complete"
        content.body = "\(timer.name) has finished"
        content.sound = UNNotificationSound.defaultCritical
        content.badge = 1
        content.userInfo = [
            "timerId": timer.id.uuidString,
            "alarmSound": alarmSound.rawValue
        ]
        
        let trigger = UNTimeIntervalNotificationTrigger(
            timeInterval: timer.remainingTime,
            repeats: false
        )
        
        let request = UNNotificationRequest(
            identifier: timer.id.uuidString,
            content: content,
            trigger: trigger
        )
        
        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                print("Failed to schedule snooze notification: \(error)")
            }
        }
    }
    
    func cancelNotification(for timer: TimerItem) {
        UNUserNotificationCenter.current().removePendingNotificationRequests(
            withIdentifiers: [timer.id.uuidString]
        )
    }
    
    func requestNotificationPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if let error = error {
                print("Notification permission error: \(error)")
            }
        }
    }
}
