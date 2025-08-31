import Foundation
import CoreData

struct PersistenceController {
    static let shared = PersistenceController()

    static var preview: PersistenceController = {
        let result = PersistenceController(inMemory: true)
        let viewContext = result.container.viewContext
        // Add sample data here if needed
        do {
            try viewContext.save()
        } catch {
            let nsError = error as NSError
            fatalError("Unresolved error \(nsError), \(nsError.userInfo)")
        }
        return result
    }()

    let container: NSPersistentContainer

    init(inMemory: Bool = false) {
        container = NSPersistentContainer(name: "ShiftMinder")
        if inMemory {
            container.persistentStoreDescriptions.first!.url = URL(fileURLWithPath: "/dev/null")
        }
        container.loadPersistentStores(completionHandler: { (storeDescription, error) in
            if let error = error as NSError? {
                fatalError("Unresolved error \(error), \(error.userInfo)")
            }
        })
        container.viewContext.automaticallyMergesChangesFromParent = true
    }
}

enum DarkModeOption: String, CaseIterable, Codable {
    case light = "light"
    case dark = "dark"
    case system = "system"
    
    var displayName: String {
        switch self {
        case .light: return "Light"
        case .dark: return "Dark"
        case .system: return "System"
        }
    }
}

enum AlarmSound: String, CaseIterable, Codable {
    case gentle = "gentle"
    case classic = "classic"
    case urgent = "urgent"
    case chime = "chime"
    case bell = "bell"
    case alert = "alert"
    case notification = "notification"
    case beep = "beep"
    
    var displayName: String {
        switch self {
        case .gentle: return "Gentle"
        case .classic: return "Classic"
        case .urgent: return "Urgent"
        case .chime: return "Chime"
        case .bell: return "Bell"
        case .alert: return "Alert"
        case .notification: return "Notification"
        case .beep: return "Beep"
        }
    }
    
    var systemSoundId: SystemSoundID {
        switch self {
        case .gentle: return 1005  // Gentle notification
        case .classic: return 1007  // Classic alarm
        case .urgent: return 1006   // Urgent alarm
        case .chime: return 1003    // Chime
        case .bell: return 1004     // Bell
        case .alert: return 1002    // Alert
        case .notification: return 1005  // Default notification
        case .beep: return 1000     // Beep
        }
    }
}

struct AppSettings: Codable {
    var darkModeOption: DarkModeOption = .system
    var reduceAnimations: Bool = false
    var textSizeMultiplier: Double = 1.0
    var hapticsEnabled: Bool = true
    var alarmSound: AlarmSound = .gentle
    var defaultCategory: TimerCategory = .prep
    
    static let `default` = AppSettings()
}

class Persistence {
    private let timersKey = "SavedTimers"
    private let settingsKey = "AppSettings"
    
    func loadTimers() -> [TimerItem] {
        guard let data = UserDefaults.standard.data(forKey: timersKey),
              let timers = try? JSONDecoder().decode([TimerItem].self, from: data) else {
            return []
        }
        return timers
    }
    
    func saveTimers(_ timers: [TimerItem]) {
        do {
            let data = try JSONEncoder().encode(timers)
            UserDefaults.standard.set(data, forKey: timersKey)
        } catch {
            print("Failed to save timers: \(error)")
        }
    }
    
    func loadSettings() -> AppSettings {
        guard let data = UserDefaults.standard.data(forKey: settingsKey),
              let settings = try? JSONDecoder().decode(AppSettings.self, from: data) else {
            return AppSettings.default
        }
        return settings
    }
    
    func saveSettings(_ settings: AppSettings) {
        do {
            let data = try JSONEncoder().encode(settings)
            UserDefaults.standard.set(data, forKey: settingsKey)
        } catch {
            print("Failed to save settings: \(error)")
        }
    }
}