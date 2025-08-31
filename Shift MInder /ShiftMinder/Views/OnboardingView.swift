import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var timerStore: TimerStore
    @EnvironmentObject var appTheme: AppTheme
    @State private var opacity: Double = 0.0
    
    var body: some View {
        VStack(spacing: 30) {
            Image(systemName: "timer")
                .font(.system(size: 80))
                .foregroundColor(.accentColor)
            
            VStack(spacing: 16) {
                Text("Welcome to Clove Timer")
                    .font(appTheme.titleFont)
                    .multilineTextAlignment(.center)
                
                Text("Create timers for your tasks and stay focused on what matters most.")
                    .font(appTheme.bodyFont)
                    .foregroundColor(appTheme.secondaryTextColor)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            
            VStack(spacing: 12) {
                FeatureRow(icon: "clock", title: "Custom Timers", description: "Set any duration from 1 minute to 1 hour")
                FeatureRow(icon: "folder", title: "Categories", description: "Organize timers by task type")
                FeatureRow(icon: "bell", title: "Smart Notifications", description: "Never miss a timer completion")
            }
            .padding(.horizontal)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(appTheme.backgroundColor)
        .ignoresSafeArea()
        .opacity(opacity)
        .onAppear {
            withAnimation(.easeIn(duration: 1.0)) {
                opacity = 1.0
            }
            
            // Auto-complete onboarding after 2.5 seconds
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                completeOnboarding()
            }
        }
    }
    
    private func completeOnboarding() {
        appTheme.darkModeOption = .system
        appTheme.hapticsEnabled = true
    }
}

struct FeatureRow: View {
    let icon: String
    let title: String
    let description: String
    @EnvironmentObject var appTheme: AppTheme
    
    var body: some View {
        HStack(spacing: 16) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(.accentColor)
                .frame(width: 30)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(appTheme.headlineFont)
                
                Text(description)
                    .font(.caption)
                    .foregroundColor(appTheme.secondaryTextColor)
            }
            
            Spacer()
        }
    }
}

#Preview {
    OnboardingView()
        .environmentObject(TimerStore())
        .environmentObject(AppTheme())
}
