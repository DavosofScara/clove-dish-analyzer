import SwiftUI

@main
struct ShiftMinderApp: App {
    let persistenceController = PersistenceController.shared
    @StateObject private var timerStore = TimerStore()
    @StateObject private var appTheme = AppTheme()

    var body: some Scene {
        WindowGroup {
            MainTabView()
                .environment(\.managedObjectContext, persistenceController.container.viewContext)
                .environmentObject(timerStore)
                .environmentObject(appTheme)
                .onAppear {
                    clearAppBadge()
                    appTheme.updateThemeFromTimerStore(timerStore)
                }
                .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
                    clearAppBadge()
                }
        }
    }
    
    private func clearAppBadge() {
        DispatchQueue.main.async {
            UIApplication.shared.applicationIconBadgeNumber = 0
            UNUserNotificationCenter.current().removeAllDeliveredNotifications()
        }
    }
}

struct MainTabView: View {
    @EnvironmentObject var timerStore: TimerStore
    @EnvironmentObject var appTheme: AppTheme
    
    var body: some View {
        TabView {
            TimerBoardView()
                .tabItem {
                    Image(systemName: "timer")
                    Text("Timers")
                }
            
            SettingsView()
                .tabItem {
                    Image(systemName: "gear")
                    Text("Settings")
                }
        }
        .background(appTheme.backgroundColor)
    }
}
