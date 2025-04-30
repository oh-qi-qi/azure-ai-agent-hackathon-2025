'use client';

import { ColumnDef } from '@tanstack/react-table';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ExternalLink, ArrowUpDown, FileText, FlaskConical } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';

// This type is used to define the shape of our data.
// You can use a Zod schema here if you want.
export type ThinkingLog = {
  id: string;
  session_id: string;
  first_query: string;
};

export const columns: ColumnDef<ThinkingLog>[] = [
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
          Session ID
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      );
    },
    cell: ({ row }) => <Badge className="bg-green-200 text-green-700">{row.original.session_id}</Badge>,
  },
  {
    accessorKey: 'first_query',
    header: 'Session Title',
    cell: ({ row }) => (
      <div>
        <p className="font-semibold">{row.original.first_query}</p>
      </div>
    ),
  },
  {
    id: 'actions',
    header: 'Action',
    cell: ({ row }) => {
      return (
        <Button asChild size="sm">
          <Link href={`/thinking-logs/${row.original.session_id}`}>
            View Agent Thought Process
            <FlaskConical className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      );
    },
  },
];
