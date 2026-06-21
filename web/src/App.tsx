import React, { useState } from 'react';
import { ShieldAlert, CheckCircle, AlertTriangle, AlertOctagon, ThumbsUp, ThumbsDown, Edit3, TrendingUp, TrendingDown, Users } from 'lucide-react';

// --- MOCK DATA ---
const MOCK_TICKETS = [
  { id: 'TKT-101', raw_text: "I forgot my password and cannot login to the dashboard.", status: "suggestions_found", trust_score: 0.88, verified: 40, total: 42, text: "Send standard password reset link macro.", rationale: "This ticket explicitly mentions forgetting a password, matching the standard account access recovery flow." },
  { id: 'TKT-102', raw_text: "My card failed to process today, please fix it.", status: "suggestions_found", trust_score: 0.55, verified: 5, total: 5, text: "Ask customer to wait 24h and retry card.", rationale: "This customer's GhostCFO account status is healthy. The resolution for transient glitches fits this profile." },
  { id: 'TKT-103', raw_text: "The entire dashboard is returning a 502 Bad Gateway.", status: "no_verified_pattern", trust_score: 0, verified: 0, total: 0, text: "", rationale: "" }
];

export default function App() {
  const [role, setRole] = useState<'agent' | 'supervisor'>('agent');
  const [activeTicket, setActiveTicket] = useState(MOCK_TICKETS[0]);

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* HEADER: Role Based Auth */}
      <header className="bg-slate-900 text-white p-4 flex justify-between items-center shadow-md">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-6 h-6 text-blue-400" />
          <h1 className="text-xl font-bold tracking-wide">ThreadSmith AI Support</h1>
        </div>
        <div className="flex gap-4 items-center">
          <span className="text-sm text-gray-400">Viewing as:</span>
          <select 
            className="bg-slate-800 border border-slate-600 rounded px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={role}
            onChange={(e) => setRole(e.target.value as any)}
          >
            <option value="agent">Support Agent</option>
            <option value="supervisor">Support Supervisor</option>
          </select>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-7xl mx-auto w-full">
        {role === 'agent' ? (
          <AgentDashboard activeTicket={activeTicket} setActiveTicket={setActiveTicket} tickets={MOCK_TICKETS} />
        ) : (
          <SupervisorDashboard />
        )}
      </main>
    </div>
  );
}

// --- AGENT DASHBOARD ---

function AgentDashboard({ activeTicket, setActiveTicket, tickets }: any) {
  return (
    <div className="flex gap-6 h-full">
      {/* TICKET QUEUE */}
      <div className="w-1/3 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col">
        <div className="bg-gray-50 p-4 border-b border-gray-200 font-semibold text-gray-700">Live Queue</div>
        <div className="flex-1 overflow-y-auto p-2">
          {tickets.map((t: any) => (
            <div 
              key={t.id} 
              onClick={() => setActiveTicket(t)}
              className={`p-4 mb-2 rounded-lg cursor-pointer transition-colors border ${activeTicket.id === t.id ? 'bg-blue-50 border-blue-200 shadow-sm' : 'bg-white border-gray-100 hover:bg-gray-50'}`}
            >
              <div className="font-bold text-gray-800 text-sm">{t.id}</div>
              <div className="text-gray-600 text-sm truncate mt-1">{t.raw_text}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ACTIVE TICKET & SUGGESTION PANEL */}
      <div className="w-2/3 flex flex-col gap-6">
        {/* Raw Ticket View */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Incoming Message • {activeTicket.id}</h2>
          <p className="text-gray-800 text-lg leading-relaxed">{activeTicket.raw_text}</p>
        </div>

        {/* Suggestion Engine View */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="bg-slate-50 p-4 border-b border-gray-200 flex justify-between items-center">
            <h2 className="font-semibold text-slate-800 flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-indigo-500" />
              ThreadSmith Resolution Engine
            </h2>
          </div>

          <div className="p-6">
            {activeTicket.status === "no_verified_pattern" ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-6 flex flex-col items-center justify-center text-center">
                <AlertOctagon className="w-12 h-12 text-red-500 mb-3" />
                <h3 className="text-lg font-bold text-red-700">NOVEL ISSUE TYPE</h3>
                <p className="text-red-600 mt-2 max-w-md">
                  There is no verified resolution pattern for this structural issue. You are in uncharted territory. 
                  Your resolution, if it works without recurrence, will become the seed pattern for this cluster.
                </p>
                <button className="mt-4 bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded-md font-medium transition-colors shadow-sm">
                  Acknowledge & Flag for Review
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-5">
                {/* Confidence Badge */}
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase">Suggested Resolution</h3>
                    <p className="text-gray-900 font-medium text-lg mt-1 bg-slate-50 p-4 rounded border border-slate-100">
                      "{activeTicket.text}"
                    </p>
                  </div>
                  {activeTicket.trust_score > 0.80 ? (
                    <div className="flex flex-col items-end">
                      <span className="inline-flex items-center gap-1 bg-emerald-100 text-emerald-800 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide">
                        <CheckCircle className="w-3 h-3" /> High Confidence
                      </span>
                      <span className="text-xs text-gray-500 mt-1 font-medium">{activeTicket.verified}/{activeTicket.total} verified</span>
                    </div>
                  ) : (
                    <div className="flex flex-col items-end">
                      <span className="inline-flex items-center gap-1 bg-amber-100 text-amber-800 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide">
                        <AlertTriangle className="w-3 h-3" /> Low Confidence (Ltd Data)
                      </span>
                      <span className="text-xs text-gray-500 mt-1 font-medium">{activeTicket.verified}/{activeTicket.total} verified</span>
                    </div>
                  )}
                </div>

                {/* AI Rationale */}
                <div className="bg-blue-50/50 border border-blue-100 rounded-lg p-4">
                  <h4 className="text-xs font-bold text-blue-800 uppercase mb-1">AI Reasoning</h4>
                  <p className="text-sm text-blue-900">{activeTicket.rationale}</p>
                </div>

                {/* Feedback Hook (Resolution Submission) */}
                <div className="border-t border-gray-100 pt-5 mt-2">
                  <p className="text-sm text-gray-600 mb-3 font-medium">How would you like to proceed?</p>
                  <div className="flex gap-3">
                    <button className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white py-2 px-4 rounded-md font-medium flex items-center justify-center gap-2 transition-colors">
                      <ThumbsUp className="w-4 h-4" /> Apply Suggestion As-Is
                    </button>
                    <button className="flex-1 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 py-2 px-4 rounded-md font-medium flex items-center justify-center gap-2 transition-colors">
                      <Edit3 className="w-4 h-4" /> Modify Suggestion
                    </button>
                    <button className="flex-1 bg-white border border-red-200 hover:bg-red-50 text-red-600 py-2 px-4 rounded-md font-medium flex items-center justify-center gap-2 transition-colors">
                      <ThumbsDown className="w-4 h-4" /> Reject & Write Own
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// --- SUPERVISOR DASHBOARD ---

function SupervisorDashboard() {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Cluster Cohesion Alerts */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <AlertOctagon className="w-5 h-5 text-purple-600" />
            <h2 className="font-bold text-gray-800">Cluster Cohesion Alerts</h2>
          </div>
          <p className="text-sm text-gray-600 mb-4">Clusters with critically low verification rates pending split review.</p>
          
          <div className="bg-purple-50 border border-purple-100 rounded-lg p-4">
            <h3 className="font-semibold text-purple-900">cluster_mixed_login</h3>
            <div className="flex justify-between items-center mt-2">
              <span className="text-xs text-purple-700 font-medium">Verification Rate: 20%</span>
              <button className="bg-purple-600 text-white text-xs px-3 py-1 rounded">Review Split</button>
            </div>
            <p className="text-xs text-purple-800 mt-2 opacity-80">AI Proposes splitting into: SSO Outage, Forgotten Password</p>
          </div>
        </div>

        {/* Agent Gaming Alerts */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <Users className="w-5 h-5 text-orange-600" />
            <h2 className="font-bold text-gray-800">Agent Gaming Alerts</h2>
          </div>
          <p className="text-sm text-gray-600 mb-4">High provisional-closure rate with disproportionate recurrence failures.</p>
          
          <div className="bg-orange-50 border border-orange-100 rounded-lg p-4">
            <h3 className="font-semibold text-orange-900">Agent ID: agt_jsmith</h3>
            <div className="flex justify-between items-center mt-2">
              <span className="text-xs text-orange-700 font-medium">Recurrence Rate: 45%</span>
              <button className="bg-orange-600 text-white text-xs px-3 py-1 rounded">Audit Tickets</button>
            </div>
            <p className="text-xs text-orange-800 mt-2 opacity-80">System Baseline Recurrence: 8%</p>
          </div>
        </div>

        {/* Trust Score Trends */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-emerald-600" />
            <h2 className="font-bold text-gray-800">Trust Score Trends</h2>
          </div>
          <p className="text-sm text-gray-600 mb-4">Tracking efficacy decay vs improvement over the last 30 days.</p>
          
          <div className="flex flex-col gap-3">
            <div className="flex justify-between items-center border-b border-gray-100 pb-2">
              <div>
                <h4 className="text-sm font-semibold text-gray-800">cluster_password</h4>
                <p className="text-xs text-gray-500">Stable</p>
              </div>
              <div className="flex items-center gap-1 text-emerald-600">
                <TrendingUp className="w-4 h-4" /> <span className="font-bold text-sm">0.88</span>
              </div>
            </div>
            
            <div className="flex justify-between items-center">
              <div>
                <h4 className="text-sm font-semibold text-gray-800">cluster_api_integration</h4>
                <p className="text-xs text-gray-500">Degrading (Recency Penalty)</p>
              </div>
              <div className="flex items-center gap-1 text-red-600">
                <TrendingDown className="w-4 h-4" /> <span className="font-bold text-sm">0.42</span>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
