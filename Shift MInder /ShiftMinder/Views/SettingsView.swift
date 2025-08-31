import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var timerStore: TimerStore
    @EnvironmentObject var appTheme: AppTheme
    
    var body: some View {
        NavigationView {
            Form {
                Section("Appearance") {
                    Picker("App Theme", selection: $timerStore.appSettings.darkModeOption) {
                        ForEach(DarkModeOption.allCases, id: \.self) { option in
                            Text(option.displayName).tag(option)
                        }
                    }
                    .onChange(of: timerStore.appSettings.darkModeOption) { newValue in
                        timerStore.updateSettingsProperty(\.darkModeOption, to: newValue)
                        timerStore.syncAppTheme(appTheme)
                    }
                    
                    Toggle("Reduce Animations", isOn: $timerStore.appSettings.reduceAnimations)
                        .onChange(of: timerStore.appSettings.reduceAnimations) { newValue in
                            timerStore.updateSettingsProperty(\.reduceAnimations, to: newValue)
                            timerStore.syncAppTheme(appTheme)
                        }
                    
                    VStack(alignment: .leading) {
                        Text("Text Size")
                        Slider(value: $timerStore.appSettings.textSizeMultiplier, in: 0.8...1.4, step: 0.1)
                        Text("\(Int(timerStore.appSettings.textSizeMultiplier * 100))%")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .onChange(of: timerStore.appSettings.textSizeMultiplier) { newValue in
                        timerStore.updateSettingsProperty(\.textSizeMultiplier, to: newValue)
                        timerStore.syncAppTheme(appTheme)
                    }
                }
                
                Section("Audio & Haptics") {
                    Toggle("Haptics", isOn: $timerStore.appSettings.hapticsEnabled)
                        .onChange(of: timerStore.appSettings.hapticsEnabled) { newValue in
                            timerStore.updateSettingsProperty(\.hapticsEnabled, to: newValue)
                            timerStore.syncAppTheme(appTheme)
                        }
                    
                    Picker("Alarm Sound", selection: $timerStore.appSettings.alarmSound) {
                        ForEach(AlarmSound.allCases, id: \.self) { sound in
                            Text(sound.displayName).tag(sound)
                        }
                    }
                }
                
                Section("Categories") {
                    Picker("Default Category", selection: $timerStore.appSettings.defaultCategory) {
                        ForEach(TimerCategory.allCases, id: \.self) { category in
                            Text(category.displayName).tag(category)
                        }
                    }
                }
                
                Section("About") {
                    HStack {
                        Text("Version")
                        Spacer()
                        Text("1.0.0")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Settings")
            .background(appTheme.backgroundColor)
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(TimerStore())
        .environmentObject(AppTheme())
}
