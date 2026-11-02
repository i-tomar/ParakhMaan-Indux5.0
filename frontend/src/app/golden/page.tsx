'use client';

import React, { useState } from 'react';
import { getStorageUrl } from '@/lib/api';
import { ProtectedImg } from '@/components/ProtectedImg';
import { productionApi } from '@/lib/industrial';
import { Banner, Button, Card, Empty, LoadState, PageHeader, useLoad } from '@/components/ui';

export default function GoldenPage() {
  const products = useLoad(() => productionApi.products());
  const [productId, setProductId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const product = products.data?.find((p) => p.id === productId) || products.data?.[0];

  const upload = async (files: FileList | null) => {
    if (!files?.[0] || !product) return;
    setError(null);
    try {
      await productionApi.addGolden(product.id, files[0], files[0].name);
      await products.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    }
  };

  return (
    <div>
      <PageHeader title="Golden References" subtitle="Known-good samples used for colour comparison, printed-design suppression and outline deviation." />
      <LoadState loading={products.loading} error={products.error} />
      {error && <div className="mb-4"><Banner tone="error">{error}</Banner></div>}
      {products.data && (products.data.length === 0 ? <Card><Empty>Create a product first, under Products & Batches.</Empty></Card> : (
        <div className="grid lg:grid-cols-[260px_1fr] gap-4">
          <Card title="Products">
            <div className="space-y-1">
              {products.data.map((p) => (
                <button key={p.id} onClick={() => setProductId(p.id)} className={`w-full text-left px-2 py-1.5 rounded-md text-xs ${product?.id === p.id ? 'bg-[#f6f5f4] font-semibold text-[#0075de]' : 'hover:bg-[#f6f5f4]'}`}>
                  {p.name} <span className="text-[#615d59]">({p.golden_references.length})</span>
                </button>
              ))}
            </div>
          </Card>
          <Card title={product?.name} actions={<label className="text-xs font-semibold text-[#0075de] cursor-pointer">Add reference<input type="file" accept="image/*" className="hidden" onChange={(e) => upload(e.target.files)} /></label>}>
            {product?.golden_references.length ? (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {product.golden_references.map((g) => (
                  <div key={g.id} className={`rounded-lg border overflow-hidden ${g.is_active ? 'border-[#0075de]' : 'border-[#e6e6e6]'}`}>
                    <ProtectedImg src={getStorageUrl(g.file_path)} alt={g.label || 'Golden reference'} className="w-full aspect-square object-cover" />
                    <div className="p-2 flex items-center justify-between gap-2">
                      <span className="text-[11px] truncate">{g.label}</span>
                      {g.is_active ? <span className="text-[10px] font-semibold text-[#0075de]">Active</span> : (
                        <Button onClick={async () => { await productionApi.activateGolden(g.id); await products.reload(); }}>Use</Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : <Empty>No golden reference for this product yet.</Empty>}
          </Card>
        </div>
      ))}
    </div>
  );
}
