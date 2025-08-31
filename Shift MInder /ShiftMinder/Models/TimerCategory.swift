import Foundation

enum TimerCategory: String, CaseIterable, Codable {
    case prep = "prep"
    case cooking = "cooking"
    case rest = "rest"
    case custom = "custom"
    
    var displayName: String {
        switch self {
        case .prep: return "Prep"
        case .cooking: return "Cooking"
        case .rest: return "Rest"
        case .custom: return "Custom"
        }
    }
    
    var icon: String {
        switch self {
        case .prep: return "knife"
        case .cooking: return "flame"
        case .rest: return "bed.double"
        case .custom: return "star"
        }
    }
}
