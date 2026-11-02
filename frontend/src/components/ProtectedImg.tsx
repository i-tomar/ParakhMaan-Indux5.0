'use client';

import React, { useEffect, useState } from 'react';
import { authHeaders, isProtectedFileUrl } from '@/lib/api';

/**
 * Stored images need a login token, and a plain <img src> cannot send one. Protected URLs are
 * fetched with the Authorization header and shown through a short-lived object URL, so the token
 * never appears in a URL. Other sources (data:, blob:, external) pass straight through.
 */
export function useProtectedSrc(src?: string | null): string | undefined {
  const [objectUrl, setObjectUrl] = useState<string | undefined>(undefined);
  const needsFetch = !!src && isProtectedFileUrl(src);

  useEffect(() => {
    if (!src || !needsFetch) return;
    let revoked = false;
    let url: string | undefined;
    fetch(src, { headers: authHeaders() })
      .then((res) => (res.ok ? res.blob() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((blob) => {
        if (revoked) return;
        url = URL.createObjectURL(blob);
        setObjectUrl(url);
      })
      .catch(() => setObjectUrl(undefined));
    return () => {
      revoked = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [src, needsFetch]);

  if (!src) return undefined;
  return needsFetch ? objectUrl : src;
}

export function ProtectedImg({ src, alt, ...rest }: React.ImgHTMLAttributes<HTMLImageElement> & { src?: string | null }) {
  const resolved = useProtectedSrc(src);
  if (!resolved) return <span aria-label={alt} className={`${rest.className ?? ''} inline-block bg-[#f6f5f4]`} />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={resolved} alt={alt} {...rest} />;
}
