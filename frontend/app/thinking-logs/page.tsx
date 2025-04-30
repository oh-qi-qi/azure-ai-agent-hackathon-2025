'use client';

import { ThinkingLog, columns } from './columns';
import { DataTable } from './data-table';
import { useEffect, useState } from 'react';
import { Skeleton } from '@/components/ui/skeleton';

export default function ThinkingLogsPage() {
  const [data, setData] = useState<ThinkingLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('/api/thinking-logs');
        if (!response.ok) {
          throw new Error('Failed to fetch thinking logs');
        }
        const result = await response.json();
        setData(result.sessions);
      } catch (error) {
        console.error('Failed to fetch thinking logs:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, []);

  if (isLoading) {
    return (
      <div className="container mx-auto py-10">
        <div className="space-y-4">
          <Skeleton className="h-8 w-[250px]" />
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-10">
      <DataTable columns={columns} data={data} />
    </div>
  );
}
