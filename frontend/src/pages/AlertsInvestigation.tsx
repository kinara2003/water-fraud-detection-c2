import React, { useState, useMemo } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  X,
  ChevronRight,
  ShieldAlert,
  Wrench,
  MapPin,
  ExternalLink,
  CheckSquare,
  Square,
  Search,
  Check,
} from 'lucide-react';

interface WorkOrder {
  id: string;
  priority: 'High' | 'Medium' | 'Low' | 'Resolved';
  sector: string;
  zoneId: string;
  suspectedIssue: string;
  targetLocation: string;
  nodeId: string;
  gps: string;
  assignedCrew: string;
  status: 'new' | 'in_progress' | 'resolved';
  step: 1 | 2 | 3 | 4;
  checklist: {
    valveBox: boolean;
    ferrule: boolean;
    ultrasonic: boolean;
  };
  outcome: 'Confirmed Illegal Bypass' | 'Confirmed Pipe Leak' | 'Normal High Consumption' | null;
  detectedAt: string;
  notes: string;
}

const INITIAL_WORK_ORDERS: WorkOrder[] = [
  {
    id: 'WO-1042',
    priority: 'High',
    sector: 'Zone 04 — East Industrial (DMA 01)',
    zoneId: 'zone-04',
    suspectedIssue: 'Unmetered Commercial Bypass (-6.0m drop)',
    targetLocation: 'Junction J_100 Chamber, Kaduwela Road',
    nodeId: 'J_100',
    gps: '6.9354° N, 79.9842° E',
    assignedCrew: 'K. Silva - NWSDB Kaduwela',
    status: 'in_progress',
    step: 3,
    checklist: {
      valveBox: true,
      ferrule: true,
      ultrasonic: false,
    },
    outcome: null,
    detectedAt: 'Today, 06:45 AM',
    notes: 'Severe pressure deficit isolated during morning cistern refill hours. Requires rapid on-site bypass verification.',
  },
  {
    id: 'WO-1043',
    priority: 'Medium',
    sector: 'Zone 07 — Biyagama Border (DMA 01)',
    zoneId: 'zone-07',
    suspectedIssue: 'Suspicious Off-Take / Secondary Tap (-4.0m)',
    targetLocation: 'Node J_700 River Perimeter Chamber',
    nodeId: 'J_700',
    gps: '6.9262° N, 79.9735° E',
    assignedCrew: 'Unassigned',
    status: 'new',
    step: 1,
    checklist: {
      valveBox: false,
      ferrule: false,
      ultrasonic: false,
    },
    outcome: null,
    detectedAt: 'Today, 09:15 AM',
    notes: 'Secondary node deficit detected; awaiting technician assignment.',
  },
  {
    id: 'WO-1039',
    priority: 'Resolved',
    sector: 'Zone 02 — Nawagamuwa North (DMA 01)',
    zoneId: 'zone-02',
    suspectedIssue: 'Service Pipe Fracture / Leakage',
    targetLocation: 'Node J_20 Nawagamuwa Devalaya Access',
    nodeId: 'J_20',
    gps: '6.9335° N, 79.9924° E',
    assignedCrew: 'M. Fernando - Leak Squad',
    status: 'resolved',
    step: 4,
    checklist: {
      valveBox: true,
      ferrule: true,
      ultrasonic: true,
    },
    outcome: 'Confirmed Pipe Leak',
    detectedAt: 'Yesterday, 02:10 PM',
    notes: 'Corroded 15mm service connection clamped; normal 20.8m pressure restored.',
  },
  {
    id: 'WO-1038',
    priority: 'Resolved',
    sector: 'Zone 01 — Town Central (DMA 01)',
    zoneId: 'zone-01',
    suspectedIssue: 'Bulk Commercial Tank Surge',
    targetLocation: 'Node J_10 Main Town Intersection',
    nodeId: 'J_10',
    gps: '6.9301° N, 80.0090° E',
    assignedCrew: 'A. Perera - Field Inspection Unit',
    status: 'resolved',
    step: 4,
    checklist: {
      valveBox: true,
      ferrule: true,
      ultrasonic: true,
    },
    outcome: 'Normal High Consumption',
    detectedAt: 'Oct 17, 10:30 AM',
    notes: 'Authorized municipal hospital storage replenishment verified; billing meter operating within calibration.',
  },
  {
    id: 'WO-1035',
    priority: 'Resolved',
    sector: 'Zone 05 — Welihinda Ridge (DMA 02)',
    zoneId: 'zone-05',
    suspectedIssue: 'Unregistered Agricultural Connection',
    targetLocation: 'Node J_1200 Hewagama Corridor',
    nodeId: 'J_1200',
    gps: '6.9229° N, 80.0112° E',
    assignedCrew: 'K. Silva - NWSDB Kaduwela',
    status: 'resolved',
    step: 4,
    checklist: {
      valveBox: true,
      ferrule: true,
      ultrasonic: true,
    },
    outcome: 'Confirmed Illegal Bypass',
    detectedAt: 'Oct 16, 07:15 AM',
    notes: 'Subterranean 2-inch PVC bypass tapping upstream of retail meter disconnected and confiscated.',
  },
  {
    id: 'WO-1032',
    priority: 'Resolved',
    sector: 'Zone 06 — Ranala Sector (DMA 02)',
    zoneId: 'zone-06',
    suspectedIssue: 'Ferrule Saddle Joint Seepage',
    targetLocation: 'Node J_3000 Welivita Highway Exit',
    nodeId: 'J_3000',
    gps: '6.9164° N, 80.0123° E',
    assignedCrew: 'M. Fernando - Leak Squad',
    status: 'resolved',
    step: 4,
    checklist: {
      valveBox: true,
      ferrule: true,
      ultrasonic: true,
    },
    outcome: 'Confirmed Pipe Leak',
    detectedAt: 'Oct 15, 11:45 AM',
    notes: 'Gasket replacement completed on ductile iron main joint.',
  },
];

const CREW_OFFICERS = [
  'K. Silva - NWSDB Kaduwela',
  'A. Perera - Field Inspection Unit',
  'M. Fernando - Leak Squad',
  'T. Bandara - Senior Technical Officer',
];

export const AlertsInvestigation: React.FC = () => {
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>(INITIAL_WORK_ORDERS);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [filterPriority, setFilterPriority] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState('');

  // Selected work order
  const selectedOrder = useMemo(() => {
    return workOrders.find((wo) => wo.id === selectedOrderId) || null;
  }, [workOrders, selectedOrderId]);

  // Dynamic counts for the summary bar
  const summaryCounts = useMemo(() => {
    const newCount = workOrders.filter((wo) => wo.status === 'new').length;
    const inProgressCount = workOrders.filter((wo) => wo.status === 'in_progress').length;
    const resolvedCount = workOrders.filter((wo) => wo.status === 'resolved').length;
    return {
      newCount,
      inProgressCount,
      resolvedCount,
    };
  }, [workOrders]);

  // Filtered rows
  const filteredOrders = useMemo(() => {
    return workOrders.filter((wo) => {
      const matchesSearch =
        searchQuery === '' ||
        wo.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        wo.sector.toLowerCase().includes(searchQuery.toLowerCase()) ||
        wo.suspectedIssue.toLowerCase().includes(searchQuery.toLowerCase()) ||
        wo.assignedCrew.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesPriority =
        filterPriority === 'All' || wo.priority.toLowerCase() === filterPriority.toLowerCase();

      return matchesSearch && matchesPriority;
    });
  }, [workOrders, searchQuery, filterPriority]);

  const handleOpenDrawer = (order: WorkOrder) => {
    setSelectedOrderId(order.id);
    setDrawerOpen(true);
  };

  const handleCloseDrawer = () => {
    setDrawerOpen(false);
  };

  // Step 2: Assign Officer
  const handleAssignCrew = (officer: string) => {
    if (!selectedOrderId) return;
    setWorkOrders((prev) =>
      prev.map((wo) =>
        wo.id === selectedOrderId
          ? {
              ...wo,
              assignedCrew: officer,
              status: wo.status === 'new' ? 'in_progress' : wo.status,
              step: wo.step < 2 ? 2 : wo.step,
            }
          : wo
      )
    );
  };

  // Step 3: Toggle Checklist Item
  const handleToggleChecklist = (item: 'valveBox' | 'ferrule' | 'ultrasonic') => {
    if (!selectedOrderId) return;
    setWorkOrders((prev) =>
      prev.map((wo) => {
        if (wo.id !== selectedOrderId) return wo;
        const nextChecklist = {
          ...wo.checklist,
          [item]: !wo.checklist[item],
        };
        const allChecked = nextChecklist.valveBox && nextChecklist.ferrule && nextChecklist.ultrasonic;
        return {
          ...wo,
          checklist: nextChecklist,
          step: allChecked && wo.step < 3 ? 3 : wo.step,
        };
      })
    );
  };

  // Step 4: Log Outcome
  const handleLogOutcome = (outcome: 'Confirmed Illegal Bypass' | 'Confirmed Pipe Leak' | 'Normal High Consumption') => {
    if (!selectedOrderId) return;
    setWorkOrders((prev) =>
      prev.map((wo) =>
        wo.id === selectedOrderId
          ? {
              ...wo,
              outcome,
              status: 'resolved',
              priority: 'Resolved',
              step: 4,
            }
          : wo
      )
    );
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
            Field Inspection Work Orders
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Operational triage and dispatch docket for physical network verifications.
          </p>
        </div>

        <div className="flex items-center space-x-2 text-xs font-mono text-slate-500 bg-white px-3 py-1.5 rounded-xl border border-slate-200 shadow-2xs">
          <span>Target Network:</span>
          <strong className="text-slate-900 font-semibold">Kaduwela DMAs 01 & 02</strong>
        </div>
      </div>

      {/* 1. SIMPLE SUMMARY BAR */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Total Alerts:
            </span>
            <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
              {/* 1 New */}
              <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                <span className="w-2 h-2 rounded-full bg-blue-600" />
                <span>{summaryCounts.newCount} New</span>
              </span>

              <span className="text-slate-300">|</span>

              {/* 1 In Progress */}
              <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                <span>{summaryCounts.inProgressCount} In Progress</span>
              </span>

              <span className="text-slate-300">|</span>

              {/* 4 Resolved this week */}
              <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>{summaryCounts.resolvedCount} Resolved this week</span>
              </span>
            </div>
          </div>

          {/* Quick Filter & Search Bar */}
          <div className="flex items-center space-x-3">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search work orders..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-blue-500 w-44 sm:w-56"
              />
            </div>

            <select
              value={filterPriority}
              onChange={(e) => setFilterPriority(e.target.value)}
              className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
            >
              <option value="All">All Priorities</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Resolved">Resolved</option>
            </select>
          </div>
        </div>
      </div>

      {/* 2. CLEAN WORK-ORDER TABLE */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900 flex items-center space-x-2">
              <Wrench className="w-4 h-4 text-blue-600" />
              <span>Active Field Verification Ledger</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Click any ticket row to view the 4-step investigation checklist and log field outcomes.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-400 font-medium">
            Showing {filteredOrders.length} tickets
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 text-[11px] uppercase font-bold text-slate-500 border-b border-slate-200">
              <tr>
                <th className="py-3.5 px-4">Priority</th>
                <th className="py-3.5 px-4">Sector</th>
                <th className="py-3.5 px-4">Suspected Issue</th>
                <th className="py-3.5 px-4">Target Location</th>
                <th className="py-3.5 px-4">Assigned Crew</th>
                <th className="py-3.5 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {filteredOrders.map((wo) => {
                const isZone04High = wo.zoneId === 'zone-04' && wo.priority === 'High';
                const isResolved = wo.status === 'resolved';

                return (
                  <tr
                    key={wo.id}
                    onClick={() => handleOpenDrawer(wo)}
                    className={`transition-colors cursor-pointer group ${
                      isZone04High
                        ? 'border-l-4 border-l-rose-500 bg-rose-50/20 hover:bg-rose-50/40'
                        : isResolved
                        ? 'bg-white hover:bg-slate-50/80'
                        : 'bg-white hover:bg-slate-50'
                    }`}
                  >
                    {/* Column 1: Priority */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {wo.priority === 'High' ? (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-rose-100 text-rose-700 border border-rose-200">
                          <AlertTriangle className="w-3 h-3 text-rose-600 shrink-0" />
                          <span>P1 High</span>
                        </span>
                      ) : wo.priority === 'Medium' ? (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                          <Clock className="w-3 h-3 text-amber-600 shrink-0" />
                          <span>P2 Medium</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
                          <span>Resolved</span>
                        </span>
                      )}
                    </td>

                    {/* Column 2: Sector */}
                    <td className="py-3.5 px-4">
                      <div className="font-bold text-slate-900 group-hover:text-blue-600 transition-colors">
                        {wo.sector}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                        Ref: {wo.id}
                      </div>
                    </td>

                    {/* Column 3: Suspected Issue */}
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-slate-800">
                        {wo.suspectedIssue}
                      </div>
                      {wo.outcome && (
                        <div className="text-[10px] font-bold text-emerald-700 mt-0.5">
                          Outcome: {wo.outcome}
                        </div>
                      )}
                    </td>

                    {/* Column 4: Target Location */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center space-x-1 text-slate-700">
                        <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate max-w-[200px]">{wo.targetLocation}</span>
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                        {wo.nodeId} • {wo.gps}
                      </div>
                    </td>

                    {/* Column 5: Assigned Crew */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center space-x-1.5">
                        <div
                          className={`w-2 h-2 rounded-full ${
                            wo.assignedCrew !== 'Unassigned' ? 'bg-emerald-500' : 'bg-slate-300'
                          }`}
                        />
                        <span
                          className={`font-medium ${
                            wo.assignedCrew !== 'Unassigned' ? 'text-slate-800' : 'text-slate-400 italic'
                          }`}
                        >
                          {wo.assignedCrew}
                        </span>
                      </div>
                    </td>

                    {/* Column 6: Action */}
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenDrawer(wo);
                        }}
                        className={`inline-flex items-center space-x-1.5 py-1.5 px-3 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                          isZone04High
                            ? 'bg-rose-600 hover:bg-rose-700 text-white shadow-2xs'
                            : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                        }`}
                      >
                        <span>Manage</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. CLICK-TO-OPEN INSPECTION DRAWER (Slide-out Side Panel) */}
      {drawerOpen && selectedOrder && (
        <div className="fixed inset-0 z-50 overflow-hidden">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity"
            onClick={handleCloseDrawer}
          />

          <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
            <div className="w-screen max-w-md sm:max-w-xl bg-white border-l border-slate-200 shadow-2xl flex flex-col">
              {/* Drawer Header */}
              <div className="p-5 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-100 text-blue-800">
                      Work Order {selectedOrder.id}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        selectedOrder.priority === 'High'
                          ? 'bg-rose-100 text-rose-700'
                          : selectedOrder.priority === 'Medium'
                          ? 'bg-amber-100 text-amber-700'
                          : 'bg-emerald-100 text-emerald-700'
                      }`}
                    >
                      {selectedOrder.priority} Priority
                    </span>
                  </div>
                  <h2 className="text-base font-bold text-slate-900 mt-1">
                    {selectedOrder.sector}
                  </h2>
                </div>

                <button
                  onClick={handleCloseDrawer}
                  className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
                  aria-label="Close panel"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Drawer Body (Scrollable) */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* Location & Diagnostic Overview Box */}
                <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-2 text-xs">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-slate-400 uppercase font-semibold text-[10px] block">
                        Suspected Anomaly
                      </span>
                      <strong className="text-slate-900 font-bold block text-sm">
                        {selectedOrder.suspectedIssue}
                      </strong>
                    </div>
                    <span className="text-slate-400 font-mono text-[11px]">
                      {selectedOrder.detectedAt}
                    </span>
                  </div>

                  <div className="pt-2 border-t border-slate-200/80 flex items-center justify-between text-slate-600">
                    <span className="flex items-center space-x-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-400" />
                      <span>{selectedOrder.targetLocation}</span>
                    </span>
                    <a
                      href={`https://www.google.com/maps?q=${selectedOrder.gps.replace(/[^\d.,]/g, '')}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline flex items-center space-x-1 font-semibold"
                    >
                      <span>Maps</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </div>

                {/* 4-STEP PROGRESS BAR / WORKFLOW */}
                <div className="space-y-3">
                  <span className="text-xs font-bold text-slate-900 uppercase tracking-wider block">
                    4-Step Inspection Lifecycle
                  </span>

                  {/* Visual Progress Steps Header */}
                  <div className="grid grid-cols-4 gap-2 text-center text-[11px] font-bold">
                    <div className="p-2 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200">
                      1. Alert
                    </div>
                    <div
                      className={`p-2 rounded-lg border ${
                        selectedOrder.assignedCrew !== 'Unassigned'
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-slate-100 text-slate-500 border-slate-200'
                      }`}
                    >
                      2. Crew
                    </div>
                    <div
                      className={`p-2 rounded-lg border ${
                        selectedOrder.checklist.valveBox &&
                        selectedOrder.checklist.ferrule &&
                        selectedOrder.checklist.ultrasonic
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : selectedOrder.assignedCrew !== 'Unassigned'
                          ? 'bg-amber-50 text-amber-700 border-amber-200 animate-pulse'
                          : 'bg-slate-100 text-slate-500 border-slate-200'
                      }`}
                    >
                      3. Visit
                    </div>
                    <div
                      className={`p-2 rounded-lg border ${
                        selectedOrder.outcome
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-slate-100 text-slate-500 border-slate-200'
                      }`}
                    >
                      4. Outcome
                    </div>
                  </div>
                </div>

                {/* STEP 1: Alert Detected (Automatic - Completed) */}
                <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-xs">
                        ✓
                      </span>
                      <h3 className="text-xs font-bold text-slate-900">
                        Step 1: Alert Detected
                      </h3>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Automatic — Completed
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 pl-8 leading-relaxed">
                    Digital twin flagged statistical drop at Node {selectedOrder.nodeId}. Evidence assembled from hydraulic residuals and temporal recurrence.
                  </p>
                </div>

                {/* STEP 2: Crew Assigned (Dropdown to select Officer) */}
                <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs ${
                          selectedOrder.assignedCrew !== 'Unassigned'
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-blue-100 text-blue-700'
                        }`}
                      >
                        2
                      </span>
                      <h3 className="text-xs font-bold text-slate-900">
                        Step 2: Crew Assigned
                      </h3>
                    </div>
                    <span className="text-[11px] text-slate-400 font-medium">
                      Select Inspection Officer
                    </span>
                  </div>

                  <div className="pl-8 space-y-2">
                    <label className="block text-xs font-semibold text-slate-700">
                      Assigned Officer / Unit:
                    </label>
                    <select
                      value={selectedOrder.assignedCrew}
                      onChange={(e) => handleAssignCrew(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-blue-500 cursor-pointer"
                    >
                      <option value="Unassigned">-- Select Officer --</option>
                      {CREW_OFFICERS.map((officer) => (
                        <option key={officer} value={officer}>
                          {officer}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* STEP 3: Physical Site Visit (Checklist) */}
                <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs ${
                          selectedOrder.checklist.valveBox &&
                          selectedOrder.checklist.ferrule &&
                          selectedOrder.checklist.ultrasonic
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-amber-100 text-amber-700'
                        }`}
                      >
                        3
                      </span>
                      <h3 className="text-xs font-bold text-slate-900">
                        Step 3: Physical Site Visit Checklist
                      </h3>
                    </div>
                    <span className="text-[11px] text-slate-400 font-medium">
                      Tap to check off
                    </span>
                  </div>

                  <div className="pl-8 space-y-2.5">
                    {/* Check valve box */}
                    <button
                      type="button"
                      onClick={() => handleToggleChecklist('valveBox')}
                      className={`w-full p-2.5 rounded-xl border text-left flex items-start space-x-2.5 transition-all cursor-pointer ${
                        selectedOrder.checklist.valveBox
                          ? 'bg-emerald-50/60 border-emerald-300 text-emerald-900'
                          : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      {selectedOrder.checklist.valveBox ? (
                        <CheckSquare className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                      ) : (
                        <Square className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                      )}
                      <div>
                        <span className="text-xs font-bold block">Check valve box</span>
                        <span className="text-[11px] text-slate-500 block">
                          Inspect chamber pit for unauthorized bypass junctions or bypass valves.
                        </span>
                      </div>
                    </button>

                    {/* Inspect ferrule connection */}
                    <button
                      type="button"
                      onClick={() => handleToggleChecklist('ferrule')}
                      className={`w-full p-2.5 rounded-xl border text-left flex items-start space-x-2.5 transition-all cursor-pointer ${
                        selectedOrder.checklist.ferrule
                          ? 'bg-emerald-50/60 border-emerald-300 text-emerald-900'
                          : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      {selectedOrder.checklist.ferrule ? (
                        <CheckSquare className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                      ) : (
                        <Square className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                      )}
                      <div>
                        <span className="text-xs font-bold block">Inspect ferrule connection</span>
                        <span className="text-[11px] text-slate-500 block">
                          Inspect subterranean ferrule saddle clamp and unmetered branching tees.
                        </span>
                      </div>
                    </button>

                    {/* Ultrasonic flow verification */}
                    <button
                      type="button"
                      onClick={() => handleToggleChecklist('ultrasonic')}
                      className={`w-full p-2.5 rounded-xl border text-left flex items-start space-x-2.5 transition-all cursor-pointer ${
                        selectedOrder.checklist.ultrasonic
                          ? 'bg-emerald-50/60 border-emerald-300 text-emerald-900'
                          : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      {selectedOrder.checklist.ultrasonic ? (
                        <CheckSquare className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                      ) : (
                        <Square className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                      )}
                      <div>
                        <span className="text-xs font-bold block">Ultrasonic flow verification</span>
                        <span className="text-[11px] text-slate-500 block">
                          Clamp portable flow meter on pipe to record transient velocity (0.06 L/s expected).
                        </span>
                      </div>
                    </button>
                  </div>
                </div>

                {/* STEP 4: Outcome Logged (Three Large, Easy-to-Tap Buttons) */}
                <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs ${
                          selectedOrder.outcome
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        4
                      </span>
                      <h3 className="text-xs font-bold text-slate-900">
                        Step 4: Outcome Logged
                      </h3>
                    </div>
                    {selectedOrder.outcome && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                        Finalized
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-slate-600 pl-8 leading-relaxed">
                    Select final verification verdict to update municipal records and retraining dataset:
                  </p>

                  <div className="pl-8 space-y-2 pt-1">
                    {/* Button 1: Confirmed Illegal Bypass */}
                    <button
                      type="button"
                      onClick={() => handleLogOutcome('Confirmed Illegal Bypass')}
                      className={`w-full py-3 px-4 rounded-xl font-bold text-xs flex items-center justify-between transition-all cursor-pointer ${
                        selectedOrder.outcome === 'Confirmed Illegal Bypass'
                          ? 'bg-rose-600 text-white shadow-sm ring-2 ring-rose-400'
                          : 'bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200'
                      }`}
                    >
                      <div className="flex items-center space-x-2">
                        <ShieldAlert className="w-4 h-4" />
                        <span>Confirmed Illegal Bypass</span>
                      </div>
                      {selectedOrder.outcome === 'Confirmed Illegal Bypass' && <Check className="w-4 h-4" />}
                    </button>

                    {/* Button 2: Confirmed Pipe Leak */}
                    <button
                      type="button"
                      onClick={() => handleLogOutcome('Confirmed Pipe Leak')}
                      className={`w-full py-3 px-4 rounded-xl font-bold text-xs flex items-center justify-between transition-all cursor-pointer ${
                        selectedOrder.outcome === 'Confirmed Pipe Leak'
                          ? 'bg-amber-600 text-white shadow-sm ring-2 ring-amber-400'
                          : 'bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200'
                      }`}
                    >
                      <div className="flex items-center space-x-2">
                        <Wrench className="w-4 h-4" />
                        <span>Confirmed Pipe Leak</span>
                      </div>
                      {selectedOrder.outcome === 'Confirmed Pipe Leak' && <Check className="w-4 h-4" />}
                    </button>

                    {/* Button 3: Normal High Consumption */}
                    <button
                      type="button"
                      onClick={() => handleLogOutcome('Normal High Consumption')}
                      className={`w-full py-3 px-4 rounded-xl font-bold text-xs flex items-center justify-between transition-all cursor-pointer ${
                        selectedOrder.outcome === 'Normal High Consumption'
                          ? 'bg-emerald-600 text-white shadow-sm ring-2 ring-emerald-400'
                          : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200'
                      }`}
                    >
                      <div className="flex items-center space-x-2">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>Normal High Consumption</span>
                      </div>
                      {selectedOrder.outcome === 'Normal High Consumption' && <Check className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Drawer Footer */}
              <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
                <span className="text-xs text-slate-500 font-mono">
                  Docket: {selectedOrder.id}
                </span>
                <button
                  onClick={handleCloseDrawer}
                  className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold transition-colors cursor-pointer"
                >
                  Close Panel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AlertsInvestigation;
