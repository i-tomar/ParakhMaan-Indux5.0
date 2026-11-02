'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Building2, Package, Users, Cpu, Plus, KeyRound, Copy, AlertCircle, CheckCircle2, RefreshCw } from 'lucide-react';
import { adminApi, orgApi } from '@/lib/api';
import { can, ROLE_LABELS } from '@/lib/auth';
import { useAuthUser } from '@/lib/useAuth';
import { formatDateTime } from '@/lib/formatters';
import { EdgeDevice, ManagedUser, PlantNode, Product } from '@/lib/types';

type Tab = 'STRUCTURE' | 'PRODUCTS' | 'USERS' | 'DEVICES';

const input = 'px-3 py-2 border border-[#e6e6e6] rounded-md focus:outline-none focus:border-[#0075de] bg-[#f6f5f4] text-xs';
const primary = 'inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold bg-[#0075de] text-white hover:bg-[#005bab] disabled:opacity-50';
const card = 'bg-white rounded-xl border border-[#e6e6e6] p-5 elevation-0';

export default function AdminPage() {
  const user = useAuthUser();
  const [tab, setTab] = useState<Tab>('STRUCTURE');
  const [plants, setPlants] = useState<PlantNode[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [devices, setDevices] = useState<EdgeDevice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<{ name: string; key: string } | null>(null);
  const [loaded, setLoaded] = useState(false);

  const reload = async () => {
    setError(null);
    try {
      const [p, pr, u, d] = await Promise.all([orgApi.tree(), orgApi.products(true), adminApi.users(), adminApi.devices()]);
      setPlants(p);
      setProducts(pr);
      setUsers(u);
      setDevices(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load administration data');
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => {
    reload();
  }, []);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    }
  };

  const stations = useMemo(
    () => plants.flatMap((p) => p.lines.flatMap((l) => l.stations.map((s) => ({ ...s, label: `${p.name} / ${l.name} / ${s.name}` })))),
    [plants]
  );

  if (user && !can(user, 'org:manage')) {
    return <div className={`${card} text-xs text-[#615d59]`}>Administration requires the Administrator role.</div>;
  }

  const tabs: Array<{ id: Tab; label: string; icon: React.ElementType }> = [
    { id: 'STRUCTURE', label: 'Plants & Stations', icon: Building2 },
    { id: 'PRODUCTS', label: 'Products', icon: Package },
    { id: 'USERS', label: 'Users & Roles', icon: Users },
    { id: 'DEVICES', label: 'Edge Devices', icon: Cpu },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-[#000000]">Administration</h1>
        <p className="text-xs text-[#615d59] mt-0.5">
          {user?.organization_name || 'Organisation'} · plants, production lines, stations, products, users and edge inference devices
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {tabs.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
                tab === t.id ? 'bg-[#0075de] text-white shadow-xs' : 'bg-white text-[#31302e] border border-[#e6e6e6] hover:bg-[#f6f5f4]'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
        <button type="button" onClick={reload} className="ml-auto p-2 rounded-full bg-white border border-[#e6e6e6]" title="Refresh">
          <RefreshCw className="w-4 h-4 text-[#0075de]" />
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl flex items-center gap-2 text-xs text-[#991B1B]">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}
      {notice && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-xl flex items-center gap-2 text-xs text-[#166534]">
          <CheckCircle2 className="w-4 h-4" /> {notice}
        </div>
      )}

      {!loaded && (
        <div className={`${card} flex items-center gap-2 text-xs text-[#615d59]`}>
          <RefreshCw className="w-4 h-4 animate-spin text-[#0075de]" /> Loading…
        </div>
      )}
      {loaded && tab === 'STRUCTURE' && <StructureTab plants={plants} run={run} />}
      {loaded && tab === 'PRODUCTS' && <ProductsTab products={products} run={run} />}
      {loaded && tab === 'USERS' && <UsersTab users={users} currentUserId={user?.id} run={run} />}
      {loaded && tab === 'DEVICES' && (
        <DevicesTab
          devices={devices}
          stations={stations}
          newKey={newKey}
          onKey={setNewKey}
          run={run}
        />
      )}
    </div>
  );
}

type RunFn = (action: () => Promise<unknown>, success: string) => Promise<void>;

function StructureTab({ plants, run }: { plants: PlantNode[]; run: RunFn }) {
  const [plantName, setPlantName] = useState('');
  const [plantLocation, setPlantLocation] = useState('');
  const [lineName, setLineName] = useState<Record<string, string>>({});
  const [stationName, setStationName] = useState<Record<string, string>>({});

  return (
    <div className="space-y-4">
      <form
        className={`${card} flex flex-wrap items-end gap-3`}
        onSubmit={(e) => {
          e.preventDefault();
          run(() => orgApi.createPlant({ name: plantName, location: plantLocation || undefined }), `Plant "${plantName}" created`).then(() => {
            setPlantName('');
            setPlantLocation('');
          });
        }}
      >
        <div className="flex flex-col gap-1 text-xs">
          <label className="font-semibold text-[#31302e]">New plant</label>
          <input className={input} required placeholder="e.g. Pune Plant 2" value={plantName} onChange={(e) => setPlantName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1 text-xs">
          <label className="font-semibold text-[#31302e]">Location</label>
          <input className={input} placeholder="optional" value={plantLocation} onChange={(e) => setPlantLocation(e.target.value)} />
        </div>
        <button type="submit" className={primary}>
          <Plus className="w-3.5 h-3.5" /> Add plant
        </button>
      </form>

      {plants.length === 0 && <p className="text-xs text-[#615d59]">No plants yet.</p>}
      {plants.map((plant) => (
        <div key={plant.id} className={card}>
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-[#e6e6e6]">
            <div>
              <p className="font-bold text-sm text-[#000000]">{plant.name}</p>
              {plant.location && <p className="text-[11px] text-[#615d59]">{plant.location}</p>}
            </div>
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const name = lineName[plant.id] || '';
                run(() => orgApi.createLine({ plant_id: plant.id, name }), `Line "${name}" added`).then(() =>
                  setLineName((s) => ({ ...s, [plant.id]: '' }))
                );
              }}
            >
              <input
                className={input}
                required
                placeholder="New production line"
                value={lineName[plant.id] || ''}
                onChange={(e) => setLineName((s) => ({ ...s, [plant.id]: e.target.value }))}
              />
              <button type="submit" className={primary}>
                <Plus className="w-3.5 h-3.5" /> Line
              </button>
            </form>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {plant.lines.map((line) => (
              <div key={line.id} className="rounded-lg border border-[#e6e6e6] p-3 bg-[#f6f5f4]/60 space-y-2">
                <p className="font-semibold text-xs text-[#000000]">{line.name}</p>
                <div className="flex flex-wrap gap-1.5">
                  {line.stations.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      title={s.is_active ? 'Click to deactivate' : 'Click to activate'}
                      onClick={() =>
                        run(() => orgApi.updateStation(s.id, { is_active: !s.is_active }), `Station "${s.name}" ${s.is_active ? 'deactivated' : 'activated'}`)
                      }
                      className={`px-2 py-0.5 rounded-full text-[11px] border ${
                        s.is_active ? 'bg-white border-[#e6e6e6] text-[#31302e]' : 'bg-gray-100 border-gray-200 text-gray-400 line-through'
                      }`}
                    >
                      {s.name}
                    </button>
                  ))}
                  {line.stations.length === 0 && <span className="text-[11px] text-[#615d59]">No stations</span>}
                </div>
                <form
                  className="flex items-center gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const name = stationName[line.id] || '';
                    run(() => orgApi.createStation({ line_id: line.id, name }), `Station "${name}" added`).then(() =>
                      setStationName((st) => ({ ...st, [line.id]: '' }))
                    );
                  }}
                >
                  <input
                    className={`${input} flex-1`}
                    required
                    placeholder="New inspection station"
                    value={stationName[line.id] || ''}
                    onChange={(e) => setStationName((st) => ({ ...st, [line.id]: e.target.value }))}
                  />
                  <button type="submit" className={primary}>
                    <Plus className="w-3.5 h-3.5" />
                  </button>
                </form>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ProductsTab({ products, run }: { products: Product[]; run: RunFn }) {
  const [form, setForm] = useState({ sku: '', name: '', family: 'METAL_SHEET', material: '' });
  return (
    <div className="space-y-4">
      <form
        className={`${card} flex flex-wrap items-end gap-3`}
        onSubmit={(e) => {
          e.preventDefault();
          run(() => orgApi.createProduct({ ...form, material: form.material || undefined }), `Product "${form.name}" created`).then(() =>
            setForm({ sku: '', name: '', family: form.family, material: '' })
          );
        }}
      >
        <input className={input} required placeholder="SKU" value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
        <input className={input} required placeholder="Product name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className={input} placeholder="Family (e.g. DIE_CASTING)" value={form.family} onChange={(e) => setForm({ ...form, family: e.target.value })} />
        <input className={input} placeholder="Material" value={form.material} onChange={(e) => setForm({ ...form, material: e.target.value })} />
        <button type="submit" className={primary}>
          <Plus className="w-3.5 h-3.5" /> Add product
        </button>
      </form>
      <div className={`${card} p-0 overflow-hidden`}>
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-[#f6f5f4] border-b border-[#e6e6e6] text-[10px] font-bold text-[#615d59] uppercase tracking-wider">
              <th className="py-2.5 px-4">SKU</th>
              <th className="py-2.5 px-4">Name</th>
              <th className="py-2.5 px-4">Family</th>
              <th className="py-2.5 px-4">Material</th>
              <th className="py-2.5 px-4 text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#e6e6e6]">
            {products.map((p) => (
              <tr key={p.id}>
                <td className="py-2.5 px-4 font-mono">{p.sku}</td>
                <td className="py-2.5 px-4 font-semibold">{p.name}</td>
                <td className="py-2.5 px-4 text-[#615d59]">{p.family || '—'}</td>
                <td className="py-2.5 px-4 text-[#615d59]">{p.material || '—'}</td>
                <td className="py-2.5 px-4 text-right">
                  <button
                    type="button"
                    onClick={() => run(() => orgApi.updateProduct(p.id, { is_active: !p.is_active }), `Product ${p.is_active ? 'archived' : 'restored'}`)}
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${p.is_active ? 'bg-green-100 text-[#166534]' : 'bg-gray-100 text-gray-500'}`}
                  >
                    {p.is_active ? 'ACTIVE' : 'ARCHIVED'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UsersTab({ users, currentUserId, run }: { users: ManagedUser[]; currentUserId?: string; run: RunFn }) {
  const [form, setForm] = useState({ email: '', full_name: '', password: '', role: 'OPERATOR' });
  return (
    <div className="space-y-4">
      <form
        className={`${card} flex flex-wrap items-end gap-3`}
        onSubmit={(e) => {
          e.preventDefault();
          run(() => adminApi.createUser(form), `User ${form.email} created`).then(() =>
            setForm({ email: '', full_name: '', password: '', role: 'OPERATOR' })
          );
        }}
      >
        <input className={input} required type="email" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <input className={input} required placeholder="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <input
          className={input}
          required
          type="password"
          minLength={10}
          placeholder="Initial password (10+ chars)"
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        <select className={input} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {Object.entries(ROLE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        <button type="submit" className={primary}>
          <Plus className="w-3.5 h-3.5" /> Add user
        </button>
      </form>
      <div className={`${card} p-0 overflow-hidden`}>
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-[#f6f5f4] border-b border-[#e6e6e6] text-[10px] font-bold text-[#615d59] uppercase tracking-wider">
              <th className="py-2.5 px-4">User</th>
              <th className="py-2.5 px-4">Role</th>
              <th className="py-2.5 px-4">Created</th>
              <th className="py-2.5 px-4 text-right">Access</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#e6e6e6]">
            {users.map((u) => {
              const self = u.id === currentUserId;
              return (
                <tr key={u.id}>
                  <td className="py-2.5 px-4">
                    <span className="font-semibold text-[#000000]">{u.full_name}</span>
                    <span className="block text-[11px] text-[#615d59]">{u.email}</span>
                  </td>
                  <td className="py-2.5 px-4">
                    <select
                      className={input}
                      value={u.role}
                      disabled={self}
                      onChange={(e) => run(() => adminApi.updateUser(u.id, { role: e.target.value }), `${u.email} is now ${ROLE_LABELS[e.target.value]}`)}
                    >
                      {Object.entries(ROLE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="py-2.5 px-4 text-[#615d59]">{formatDateTime(u.created_at)}</td>
                  <td className="py-2.5 px-4 text-right">
                    <button
                      type="button"
                      disabled={self}
                      onClick={() => run(() => adminApi.updateUser(u.id, { is_active: !u.is_active }), `${u.email} ${u.is_active ? 'disabled' : 'enabled'}`)}
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold disabled:opacity-40 ${
                        u.is_active ? 'bg-green-100 text-[#166534]' : 'bg-red-100 text-[#991B1B]'
                      }`}
                    >
                      {u.is_active ? 'ACTIVE' : 'DISABLED'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DevicesTab({
  devices,
  stations,
  newKey,
  onKey,
  run,
}: {
  devices: EdgeDevice[];
  stations: Array<{ id: string; label: string }>;
  newKey: { name: string; key: string } | null;
  onKey: (k: { name: string; key: string } | null) => void;
  run: RunFn;
}) {
  const [name, setName] = useState('');
  const [stationId, setStationId] = useState('');
  const stationLabel = (id?: string | null) => stations.find((s) => s.id === id)?.label || '—';

  return (
    <div className="space-y-4">
      <form
        className={`${card} flex flex-wrap items-end gap-3`}
        onSubmit={(e) => {
          e.preventDefault();
          run(async () => {
            const res = await adminApi.createDevice({ name, station_id: stationId || undefined });
            onKey({ name: res.device.name, key: res.device_key });
          }, `Device "${name}" registered`).then(() => setName(''));
        }}
      >
        <input className={input} required placeholder="Device name (e.g. Cam-01 Press Line)" value={name} onChange={(e) => setName(e.target.value)} />
        <select className={input} value={stationId} onChange={(e) => setStationId(e.target.value)}>
          <option value="">No station</option>
          {stations.map((s) => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
        <button type="submit" className={primary}>
          <Plus className="w-3.5 h-3.5" /> Register device
        </button>
      </form>

      {newKey && (
        <div className="p-4 rounded-xl border border-amber-300 bg-amber-50 text-xs space-y-2">
          <p className="font-bold text-[#854D0E] flex items-center gap-1.5">
            <KeyRound className="w-4 h-4" /> Device key for {newKey.name} — shown only once
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 px-3 py-2 bg-white border border-amber-200 rounded-md font-mono break-all">{newKey.key}</code>
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(newKey.key)}
              className="p-2 rounded-md bg-white border border-amber-200"
              title="Copy"
            >
              <Copy className="w-4 h-4" />
            </button>
          </div>
          <p className="text-[#854D0E]">
            Set it as <code>EDGE_DEVICE_KEY</code> on the edge node. Only a hash is stored, so a lost key must be rotated.
          </p>
          <button type="button" onClick={() => onKey(null)} className="text-[#854D0E] underline font-semibold">
            I have stored the key
          </button>
        </div>
      )}

      <div className={`${card} p-0 overflow-hidden`}>
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-[#f6f5f4] border-b border-[#e6e6e6] text-[10px] font-bold text-[#615d59] uppercase tracking-wider">
              <th className="py-2.5 px-4">Device</th>
              <th className="py-2.5 px-4">Station</th>
              <th className="py-2.5 px-4">Key</th>
              <th className="py-2.5 px-4">Last seen</th>
              <th className="py-2.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#e6e6e6]">
            {devices.length === 0 && (
              <tr>
                <td colSpan={5} className="py-6 text-center text-[#615d59]">No edge devices registered.</td>
              </tr>
            )}
            {devices.map((d) => (
              <tr key={d.id}>
                <td className="py-2.5 px-4 font-semibold">{d.name}</td>
                <td className="py-2.5 px-4 text-[#615d59]">{stationLabel(d.station_id)}</td>
                <td className="py-2.5 px-4 font-mono text-[11px]">{d.key_prefix}…</td>
                <td className="py-2.5 px-4 text-[#615d59]">{d.last_seen_at ? formatDateTime(d.last_seen_at) : 'never'}</td>
                <td className="py-2.5 px-4 text-right space-x-1.5">
                  <button
                    type="button"
                    onClick={() =>
                      run(async () => {
                        const res = await adminApi.rotateDeviceKey(d.id);
                        onKey({ name: d.name, key: res.device_key });
                      }, `Key rotated for ${d.name}`)
                    }
                    className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#f6f5f4] border border-[#e6e6e6]"
                  >
                    ROTATE KEY
                  </button>
                  <button
                    type="button"
                    onClick={() => run(() => adminApi.updateDevice(d.id, { is_active: !d.is_active }), `${d.name} ${d.is_active ? 'disabled' : 'enabled'}`)}
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${d.is_active ? 'bg-green-100 text-[#166534]' : 'bg-red-100 text-[#991B1B]'}`}
                  >
                    {d.is_active ? 'ACTIVE' : 'DISABLED'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
