import SwiftUI

struct CreateEditTimerView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var timerStore: TimerStore
    @EnvironmentObject var appTheme: AppTheme
    
    @State private var name = ""
    @State private var durationMinutes = 5
    @State private var selectedCategory: TimerCategory = .prep
    
    let preSelectedCategory: TimerCategory?
    
    init(preSelectedCategory: TimerCategory? = nil) {
        self.preSelectedCategory = preSelectedCategory
    }
    
    var body: some View {
        NavigationView {
            Form {
                Section("Timer Details") {
                    TextField("Timer Name", text: $name)
                        .font(.title2)
                    
                    Picker("Duration", selection: $durationMinutes) {
                        ForEach([1, 2, 3, 5, 10, 15, 20, 25, 30, 45, 60], id: \.self) { minutes in
                            Text("\(minutes) min").tag(minutes)
                        }
                    }
                    
                    Picker("Category", selection: $selectedCategory) {
                        ForEach(TimerCategory.allCases, id: \.self) { category in
                            Text(category.displayName).tag(category)
                        }
                    }
                }
            }
            .navigationTitle("New Timer")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        saveTimer()
                    }
                    .disabled(name.isEmpty)
                }
            }
            .onAppear {
                if let preSelected = preSelectedCategory {
                    selectedCategory = preSelected
                } else {
                    selectedCategory = timerStore.appSettings.defaultCategory
                }
            }
        }
    }
    
    private func saveTimer() {
        let timer = TimerItem(
            name: name,
            durationMinutes: durationMinutes,
            category: selectedCategory
        )
        
        timerStore.addTimer(timer)
        dismiss()
    }
}

#Preview {
    CreateEditTimerView()
        .environmentObject(TimerStore())
        .environmentObject(AppTheme())
}
