import SwiftUI

struct TimerBoardView: View {
    @EnvironmentObject var timerStore: TimerStore
    @EnvironmentObject var appTheme: AppTheme
    @State private var selectedCategory: TimerCategory? = nil
    @State private var showingCreateTimer = false
    @State private var showingOnboarding = false
    @State private var newTimerCategory: TimerCategory? = nil
    
    var body: some View {
        NavigationView {
            VStack {
                if timerStore.timers.isEmpty {
                    OnboardingView()
                        .onAppear {
                            showingOnboarding = true
                        }
                } else {
                    CategoryPickerView(selectedCategory: $selectedCategory)
                    
                    TimerListView(selectedCategory: selectedCategory)
                }
            }
            .background(appTheme.backgroundColor)
            .navigationTitle(selectedCategory?.displayName ?? "Clove Timer")
            .toolbarColorScheme(appTheme.darkMode ? .dark : .light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: {
                        newTimerCategory = selectedCategory
                        showingCreateTimer = true
                    }) {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showingCreateTimer) {
                CreateEditTimerView(preSelectedCategory: newTimerCategory)
            }
            .onChange(of: timerStore.timers.count) { _ in
                if selectedCategory != nil {
                    selectedCategory = nil
                }
            }
        }
    }
}

struct CategoryPickerView: View {
    @Binding var selectedCategory: TimerCategory?
    @EnvironmentObject var appTheme: AppTheme
    
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                CategoryButton(
                    title: "Active",
                    isSelected: selectedCategory == nil,
                    action: { selectedCategory = nil }
                )
                
                ForEach(TimerCategory.allCases, id: \.self) { category in
                    CategoryButton(
                        title: category.displayName,
                        isSelected: selectedCategory == category,
                        action: { selectedCategory = category }
                    )
                }
            }
            .padding(.horizontal)
        }
        .padding(.vertical, 8)
    }
}

struct CategoryButton: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void
    @EnvironmentObject var appTheme: AppTheme
    
    var body: some View {
        Button(action: action) {
            Text(title)
                .font(appTheme.bodyFont)
                .foregroundColor(isSelected ? .white : appTheme.textColor)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 20)
                        .fill(isSelected ? Color.accentColor : appTheme.secondaryBackgroundColor)
                )
        }
    }
}

struct TimerListView: View {
    let selectedCategory: TimerCategory?
    @EnvironmentObject var timerStore: TimerStore
    @EnvironmentObject var appTheme: AppTheme
    
    var filteredTimers: [TimerItem] {
        if let category = selectedCategory {
            return timerStore.timers.filter { $0.category == category }
        } else {
            return timerStore.activeTimers
        }
    }
    
    var body: some View {
        List {
            ForEach(filteredTimers) { timer in
                TimerRowView(timer: timer)
                    .scaleEffect(timer.state.isCompleted ? 0.95 : 1.0)
                    .animation(.easeInOut(duration: 0.2), value: timer.state.isCompleted)
            }
        }
        .listStyle(PlainListStyle())
    }
}

struct TimerRowView: View {
    let timer: TimerItem
    @EnvironmentObject var timerStore: TimerStore
    @EnvironmentObject var appTheme: AppTheme
    
    var body: some View {
        TimerTileView(timer: timer)
            .padding(.vertical, 4)
    }
}

#Preview {
    TimerBoardView()
        .environmentObject(TimerStore())
        .environmentObject(AppTheme())
}
