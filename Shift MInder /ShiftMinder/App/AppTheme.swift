import SwiftUI

class AppTheme: ObservableObject {
    @Published var darkModeOption: DarkModeOption = .light
    @Published var reduceAnimations: Bool = false
    @Published var textSizeMultiplier: Double = 1.0
    @Published var hapticsEnabled: Bool = true
    
    @Published var backgroundColor: Color = .white
    @Published var secondaryBackgroundColor: Color = Color(.systemGray6)
    @Published var textColor: Color = .black
    @Published var secondaryTextColor: Color = .secondary
    
    var darkMode: Bool {
        switch darkModeOption {
        case .light:
            return false
        case .dark:
            return true
        case .system:
            if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene {
                return windowScene.traitCollection.userInterfaceStyle == .dark
            }
            return false
        }
    }
    
    var titleFont: Font {
        .title.weight(.bold).scaleEffect(textSizeMultiplier)
    }
    
    var headlineFont: Font {
        .headline.weight(.semibold).scaleEffect(textSizeMultiplier)
    }
    
    var bodyFont: Font {
        .body.scaleEffect(textSizeMultiplier)
    }
    
    var timerFont: Font {
        .system(size: 24, weight: .bold, design: .monospaced).scaleEffect(textSizeMultiplier)
    }
    
    init() {
        updateColors()
    }
    
    func syncWithSettings(_ settings: AppSettings) {
        darkModeOption = settings.darkModeOption
        reduceAnimations = settings.reduceAnimations
        textSizeMultiplier = settings.textSizeMultiplier
        hapticsEnabled = settings.hapticsEnabled
        updateColors()
    }
    
    func updateThemeFromTimerStore(_ timerStore: TimerStore) {
        syncWithSettings(timerStore.appSettings)
    }
    
    private func updateColors() {
        if darkMode {
            backgroundColor = Color(.systemBackground)
            secondaryBackgroundColor = Color(.secondarySystemBackground)
            textColor = Color(.label)
            secondaryTextColor = Color(.secondaryLabel)
        } else {
            backgroundColor = Color(.systemBackground)
            secondaryBackgroundColor = Color(.secondarySystemBackground)
            textColor = Color(.label)
            secondaryTextColor = Color(.secondaryLabel)
        }
    }
}
