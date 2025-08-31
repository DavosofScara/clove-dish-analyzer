import SwiftUI

struct TimerTileView: View {
    let timer: TimerItem
    @EnvironmentObject var timerStore: TimerStore
    @EnvironmentObject var appTheme: AppTheme
    
    @State private var pulseScale: CGFloat = 1.0
    @State private var pulseOpacity: Double = 1.0
    
    var body: some View {
        VStack(spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(timer.name)
                        .font(appTheme.headlineFont)
                        .foregroundColor(timer.state.isCompleted ? .white : appTheme.textColor)
                    
                    Text(timer.category.displayName)
                        .font(.caption)
                        .foregroundColor(timer.state.isCompleted ? .white.opacity(0.8) : appTheme.secondaryTextColor)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 4) {
                    Text(formatTime(timer.remainingTime))
                        .font(appTheme.timerFont)
                        .foregroundColor(timerNumbersColor)
                    
                    if timer.state.isCompleted {
                        Text("DONE!")
                            .font(.caption)
                            .fontWeight(.bold)
                            .foregroundColor(.white)
                    }
                }
            }
            
            ProgressView(value: timer.progress)
                .progressViewStyle(LinearProgressViewStyle(tint: progressColor))
                .scaleEffect(y: 2.0)
            
            HStack(spacing: 16) {
                ForEach(buttonActions, id: \.title) { action in
                    Button(action: action.action) {
                        Image(systemName: action.icon)
                            .font(.title2)
                            .foregroundColor(action.color)
                    }
                }
            }
        }
        .padding()
        .background(backgroundView)
        .cornerRadius(12)
        .scaleEffect(pulseScale)
        .opacity(pulseOpacity)
        .onAppear {
            startPulseAnimation()
        }
        .onChange(of: timer.state) { _ in
            pulseScale = 1.0
            pulseOpacity = 1.0
            startPulseAnimation()
        }
    }
    
    private var backgroundView: some View {
        Group {
            if appTheme.reduceAnimations {
                RoundedRectangle(cornerRadius: 12)
                    .fill(solidBackgroundColor)
            } else {
                RoundedRectangle(cornerRadius: 12)
                    .fill(animatedBackgroundColor)
            }
        }
    }
    
    private var solidBackgroundColor: Color {
        switch timer.state {
        case .running:
            return Color.green.opacity(0.8)
        case .expired:
            return Color.red.opacity(0.8)
        default:
            return appTheme.secondaryBackgroundColor
        }
    }
    
    private var animatedBackgroundColor: Color {
        let baseColor: Color
        let targetColor: Color
        
        switch timer.state {
        case .running:
            baseColor = Color.white
            targetColor = Color.green.opacity(0.8)
        case .expired:
            baseColor = Color.green.opacity(0.8)
            targetColor = Color.red.opacity(0.8)
        default:
            return appTheme.secondaryBackgroundColor
        }
        
        let progress = (sin(Date().timeIntervalSince1970 * 2) + 1) / 2
        
        return Color(
            red: interpolate(from: baseColor.components.red, to: targetColor.components.red, progress: progress),
            green: interpolate(from: baseColor.components.green, to: targetColor.components.green, progress: progress),
            blue: interpolate(from: baseColor.components.blue, to: targetColor.components.blue, progress: progress)
        )
    }
    
    private var timerNumbersColor: Color {
        if appTheme.reduceAnimations {
            if timer.state == .running {
                return .white
            } else {
                return appTheme.textColor
            }
        } else {
            if timer.state == .running {
                return .black
            } else if timer.state == .expired {
                return .white
            } else {
                return appTheme.textColor
            }
        }
    }
    
    private var progressColor: Color {
        switch timer.state {
        case .running:
            return .green
        case .expired:
            return .red
        default:
            return .blue
        }
    }
    
    private var buttonActions: [ButtonAction] {
        switch timer.state {
        case .idle:
            return [
                ButtonAction(title: "Start", icon: "play.fill", color: .green, action: { timerStore.startTimer(timer) })
            ]
        case .running:
            return [
                ButtonAction(title: "Pause", icon: "pause.fill", color: .orange, action: { timerStore.pauseTimer(timer) }),
                ButtonAction(title: "Stop", icon: "stop.fill", color: .red, action: { timerStore.stopTimer(timer) })
            ]
        case .paused:
            return [
                ButtonAction(title: "Resume", icon: "play.fill", color: .green, action: { timerStore.resumeTimer(timer) }),
                ButtonAction(title: "Stop", icon: "stop.fill", color: .red, action: { timerStore.stopTimer(timer) })
            ]
        case .expired:
            return [
                ButtonAction(title: "Snooze", icon: "clock.arrow.circlepath", color: .blue, action: { timerStore.snoozeTimer(timer) }),
                ButtonAction(title: "Reset", icon: "arrow.clockwise", color: .gray, action: { timerStore.resetTimer(timer) })
            ]
        }
    }
    
    private func startPulseAnimation() {
        guard !appTheme.reduceAnimations else { return }
        
        let delay = Double.random(in: 0.0...0.4)
        
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
            withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                pulseScale = 1.05
                pulseOpacity = 0.8
            }
        }
    }
    
    private func interpolate(from: Double, to: Double, progress: Double) -> Double {
        return from + (to - from) * progress
    }
}

struct ButtonAction {
    let title: String
    let icon: String
    let color: Color
    let action: () -> Void
}

extension Color {
    var components: (red: Double, green: Double, blue: Double) {
        let uiColor = UIColor(self)
        var red: CGFloat = 0
        var green: CGFloat = 0
        var blue: CGFloat = 0
        var alpha: CGFloat = 0
        
        uiColor.getRed(&red, green: &green, blue: &blue, alpha: &alpha)
        
        return (Double(red), Double(green), Double(blue))
    }
}

#Preview {
    TimerTileView(timer: TimerItem(name: "Test Timer", durationMinutes: 5, category: .prep))
        .environmentObject(TimerStore())
        .environmentObject(AppTheme())
}
