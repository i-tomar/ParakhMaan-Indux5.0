'use client';

import React from 'react';
import { getSessionUser } from '@/lib/api';
import { edgeApi } from '@/lib/industrial';
import { Card, LoadState, PageHeader, Table, useLoad } from '@/components/ui';

export default function SettingsPage() {
  const edge = useLoad(() => edgeApi.status());
  const e = edge.data;
  const user = getSessionUser();
  return (
    <div>
      <PageHeader title="Settings" subtitle="Account, runtime and hardware status. Configuration is set by environment variables on the edge node." />
      <LoadState loading={edge.loading} error={edge.error} />
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Account">
          <Table columns={['Field', 'Value']} rows={[['Name', user?.full_name], ['Email', user?.email], ['Role', user?.role]]} />
        </Card>
        {e && (
          <>
            <Card title="Device">
              <Table columns={['Field', 'Value']} rows={[
                ['System', `${e.device.system} ${e.device.release}`], ['Architecture', e.device.machine], ['CPU cores', e.device.cpu_count],
                ['Python', e.device.python], ['ONNX Runtime', e.runtime.onnxruntime], ['OpenCV', e.runtime.opencv],
                ['Execution providers', e.runtime.available_providers.join(', ')], ['Peak memory', `${e.process.peak_memory_mb} MB`],
              ]} />
            </Card>
            <Card title="Hardware support">
              <p className="text-xs font-semibold mb-1">Tested</p>
              <ul className="text-xs list-disc pl-4 mb-3">{e.verified_hardware.map((h: string) => <li key={h}>{h}</li>)}</ul>
              <p className="text-xs font-semibold mb-1">Not tested</p>
              <ul className="text-xs list-disc pl-4 text-[#615d59]">{e.unverified_hardware.map((h: string) => <li key={h}>{h}</li>)}</ul>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
