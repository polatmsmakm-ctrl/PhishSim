import SwiftUI

struct Campaign: Codable, Identifiable {
    let id: Int
    let name: String
    let training_url: String
    let status: String
    let created_at: String?
    let updated_at: String?
}
struct CampaignEnvelope: Codable { let campaigns: [Campaign] }
struct Report: Codable, Identifiable {
    let id: Int
    let name: String
    let clicks: Int
    let reports: Int
    let participants: Int
    let unique_reporters: Int
    let discovery_rate: Double
}
struct ReportEnvelope: Codable { let reports: [Report] }
struct TokenResponse: Codable { let token: String; let username: String }
struct IDResponse: Codable { let id: Int }
struct APIError: Codable { let error: String }

@MainActor final class AppModel: ObservableObject {
    @Published var baseURL = UserDefaults.standard.string(forKey: "baseURL") ?? "http://192.168.1.10:8765"
    @Published var username = ""
    @Published var password = ""
    @Published var token: String? = nil
    @Published var campaigns: [Campaign] = []
    @Published var reports: [Report] = []
    @Published var error = ""
    @Published var busy = false

    private func request<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil, authenticated: Bool = true) async throws -> T {
        guard let root = URL(string: baseURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              ["http", "https"].contains(root.scheme ?? ""), root.host != nil else {
            throw NSError(domain: "PhishSim", code: 1, userInfo: [NSLocalizedDescriptionKey: "عنوان الخادم غير صحيح."])
        }
        let base = root.absoluteString.hasSuffix("/") ? String(root.absoluteString.dropLast()) : root.absoluteString
        guard let url = URL(string: base + "/" + path) else { throw URLError(.badURL) }
        var req = URLRequest(url: url, timeoutInterval: 12)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if authenticated, let token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body { req.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let (data, response) = try await URLSession.shared.data(for: req)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let message = (try? JSONDecoder().decode(APIError.self, from: data).error) ?? "تعذر الاتصال بالخادم (\(status))."
            throw NSError(domain: "PhishSim", code: status, userInfo: [NSLocalizedDescriptionKey: message])
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
    func login() async {
        busy = true; error = ""
        defer { busy = false }
        do {
            let result: TokenResponse = try await request("api/login", method: "POST", body: ["username": username, "password": password], authenticated: false)
            token = result.token; password = ""
            await refresh()
        } catch { self.error = error.localizedDescription }
    }
    func refresh() async {
        guard token != nil else { return }
        do {
            let c: CampaignEnvelope = try await request("api/campaigns")
            let r: ReportEnvelope = try await request("api/reports")
            campaigns = c.campaigns; reports = r.reports
        } catch { self.error = error.localizedDescription }
    }
    func create(name: String, url: String) async {
        do { let _: IDResponse = try await request("api/campaigns", method: "POST", body: ["name": name, "url": url]); await refresh() }
        catch { self.error = error.localizedDescription }
    }
    func action(_ campaign: Campaign, _ action: String) async {
        do { let _: EmptyResponse = try await request("api/campaigns", method: "PATCH", body: ["campaign_id": campaign.id, "action": action]); await refresh() }
        catch { self.error = error.localizedDescription }
    }
    func record(_ campaign: Campaign, participant: String, kind: String) async {
        do { let _: EmptyResponse = try await request("api/events", method: "POST", body: ["campaign_id": campaign.id, "participant_ref": participant, "event_type": kind]); await refresh() }
        catch { self.error = error.localizedDescription }
    }
    func saveURL() { UserDefaults.standard.set(baseURL, forKey: "baseURL") }
    func logout() {
        Task {
            if token != nil { let _: EmptyResponse? = try? await request("api/logout", method: "POST", body: [:]) }
            token = nil; campaigns = []; reports = []
        }
    }
}
struct EmptyResponse: Codable { let ok: Bool? }

struct ContentView: View {
    @StateObject private var model = AppModel()
    @State private var showCreate = false
    @State private var selected: Campaign? = nil
    var body: some View {
        NavigationStack {
            Group {
                if model.token == nil { loginView }
                else { dashboard }
            }
            .navigationTitle("PhishSim")
            .toolbar {
                if model.token != nil {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    }
                }
            }
            .sheet(isPresented: $showCreate) { CreateCampaignView(model: model) }
            .sheet(item: $selected) { campaign in CampaignDetailView(model: model, campaign: campaign) }
            .alert("تنبيه", isPresented: Binding(get: { !model.error.isEmpty }, set: { if !$0 { model.error = "" } })) {
                Button("حسناً") { model.error = "" }
            } message: { Text(model.error) }
            .environment(\.layoutDirection, .rightToLeft)
        }
        .tint(Color(red: 0.25, green: 0.55, blue: 0.95))
    }
    private var loginView: some View {
        Form {
            Section("الاتصال بالخادم") {
                TextField("عنوان الخادم، مثال: http://192.168.1.10:8765", text: $model.baseURL).textInputAutocapitalization(.never).keyboardType(.URL).autocorrectionDisabled()
                    .onChange(of: model.baseURL) { _ in model.saveURL() }
            }
            Section("تسجيل الدخول") {
                TextField("اسم المستخدم", text: $model.username).textInputAutocapitalization(.never).autocorrectionDisabled()
                SecureField("كلمة المرور", text: $model.password)
                Button { Task { await model.login() } } label: {
                    HStack { Spacer(); if model.busy { ProgressView() }; Text("دخول"); Spacer() }
                }.disabled(model.busy || model.username.isEmpty || model.password.isEmpty)
            }
            Section { Text("يتصل التطبيق بخادم PhishSim على شبكة محلية موثوقة. لا تفتح منفذ الخادم على الإنترنت.").font(.footnote).foregroundStyle(.secondary) }
        }
    }
    private var dashboard: some View {
        List {
            Section {
                HStack {
                    StatTile(title: "الحملات", value: "\(model.campaigns.count)", icon: "paperplane")
                    StatTile(title: "النقرات", value: "\(model.reports.reduce(0) { $0 + $1.clicks })", icon: "cursorarrow.click")
                    StatTile(title: "البلاغات", value: "\(model.reports.reduce(0) { $0 + $1.reports })", icon: "flag")
                }.listRowInsets(EdgeInsets())
            }
            Section("الحملات") {
                if model.campaigns.isEmpty { ContentUnavailableView("لا توجد حملات", systemImage: "tray", description: Text("أنشئ حملة تدريبية للبدء.")) }
                ForEach(model.campaigns) { campaign in
                    Button { selected = campaign } label: {
                        VStack(alignment: .leading, spacing: 7) {
                            HStack { Text(campaign.name).font(.headline); Spacer(); StatusPill(status: campaign.status) }
                            Text(campaign.training_url).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                            if let report = model.reports.first(where: { $0.id == campaign.id }) {
                                Text("مشاركون: \(report.participants)  •  نقرات: \(report.clicks)  •  بلاغات: \(report.reports)").font(.caption2).foregroundStyle(.secondary)
                            }
                        }.padding(.vertical, 4)
                    }.buttonStyle(.plain)
                }
            }
            Section {
                Button(role: .destructive) { model.logout() } label: { Label("تسجيل الخروج", systemImage: "rectangle.portrait.and.arrow.right") }
            }
        }
        .refreshable { await model.refresh() }
        .toolbar { ToolbarItem(placement: .topBarLeading) { Button { showCreate = true } label: { Image(systemName: "plus") } } }
    }
}

struct StatTile: View {
    let title: String; let value: String; let icon: String
    var body: some View { VStack(spacing: 6) { Image(systemName: icon).foregroundStyle(.blue); Text(value).font(.title2.bold()); Text(title).font(.caption).foregroundStyle(.secondary) }.frame(maxWidth: .infinity).padding(.vertical, 12).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12)) }
}
struct StatusPill: View {
    let status: String
    var label: String { ["draft":"مسودة", "active":"نشطة", "paused":"متوقفة", "completed":"مكتملة"][status] ?? status }
    var color: Color { status == "active" ? .green : status == "completed" ? .gray : status == "paused" ? .orange : .blue }
    var body: some View { Text(label).font(.caption2.bold()).padding(.horizontal, 9).padding(.vertical, 5).background(color.opacity(0.13), in: Capsule()).foregroundStyle(color) }
}
struct CreateCampaignView: View {
    @ObservedObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var url = "https://training.example.org/awareness"
    var body: some View {
        NavigationStack {
            Form {
                Section("بيانات الحملة") {
                    TextField("اسم الحملة", text: $name)
                    TextField("رابط صفحة التوعية التابعة لك", text: $url).textInputAutocapitalization(.never).keyboardType(.URL).autocorrectionDisabled()
                }
                Section { Text("تنشأ كل حملة كمسودة. لا تستخدم نطاقات أو صفحات لا تملكها أو لا تملك تصريحاً لاختبارها.").font(.footnote).foregroundStyle(.secondary) }
            }
            .navigationTitle("حملة جديدة")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("إلغاء") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("إنشاء") { Task { await model.create(name: name, url: url); dismiss() } }.disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || url.isEmpty) }
            }
        }.environment(\.layoutDirection, .rightToLeft)
    }
}
struct CampaignDetailView: View {
    @ObservedObject var model: AppModel
    let campaign: Campaign
    @Environment(\.dismiss) private var dismiss
    @State private var participant = "test-user-01"
    var report: Report? { model.reports.first { $0.id == campaign.id } }
    var body: some View {
        NavigationStack {
            List {
                Section("تفاصيل الحملة") {
                    LabeledContent("الاسم", value: campaign.name)
                    LabeledContent("الحالة") { StatusPill(status: campaign.status) }
                    LabeledContent("رابط التوعية", value: campaign.training_url).textSelection(.enabled)
                }
                Section("النتائج") {
                    LabeledContent("المشاركون", value: "\(report?.participants ?? 0)")
                    LabeledContent("النقرات التجريبية", value: "\(report?.clicks ?? 0)")
                    LabeledContent("البلاغات", value: "\(report?.reports ?? 0)")
                    LabeledContent("معدل الاكتشاف", value: "\(report?.discovery_rate ?? 0, specifier: "%.1f")٪")
                }
                if campaign.status == "active" {
                    Section("تسجيل تفاعل تجريبي") {
                        TextField("معرّف تجريبي غير حقيقي", text: $participant).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Button("تسجيل نقرة تدريبية") { Task { await model.record(campaign, participant: participant, kind: "click"); dismiss() } }
                        Button("تسجيل بلاغ تدريبي") { Task { await model.record(campaign, participant: participant, kind: "report"); dismiss() } }
                    }
                }
                Section("إدارة الحالة") {
                    if campaign.status == "draft" || campaign.status == "paused" { Button("تفعيل / استئناف") { Task { await model.action(campaign, "resume"); dismiss() } } }
                    if campaign.status == "active" { Button("إيقاف الحملة") { Task { await model.action(campaign, "pause"); dismiss() } }; Button("إكمال الحملة") { Task { await model.action(campaign, "complete"); dismiss() } } }
                }
            }
            .navigationTitle("الحملة #\(campaign.id)")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("إغلاق") { dismiss() } } }
        }.environment(\.layoutDirection, .rightToLeft)
    }
}
