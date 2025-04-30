'use client';

import { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ArrowUpDown, CloudDownload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export type Report = {
  report_id: string;
  blob_url: string;
  session_id: string;
};

export const columns: ColumnDef<Report>[] = [
  {
    id: 'select',
    header: ({ table }) => (
      <Checkbox
        checked={table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && 'indeterminate')}
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
        aria-label="Select all"
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label="Select row"
      />
    ),
    enableSorting: false,
    enableHiding: false,
  },
  {
    accessorKey: 'session_id',
    header: ({ column }) => {
      return (
        <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
          Report ID
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      );
    },
    cell: ({ row }) => <Badge className="bg-blue-200 text-blue-700">{row.original.session_id}</Badge>,
  },
  {
    id: 'actions',
    header: 'Action',
    cell: ({ row }) => {
      return (
        <Button asChild size="sm">
          <a href={row.original.blob_url} target="_blank" rel="noopener noreferrer">
            Download Report
            <CloudDownload className="ml-2 h-4 w-4" />
          </a>
        </Button>
      );
    },
  },
];
