import { ClipboardList } from 'lucide-react'
import { useState } from 'react'
import { EmptyState } from '@/components/shared/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuditLogSearch } from '@/features/audit/hooks'

const PAGE_SIZE = 50

function formatEntity(entityType: string, entityId: string | null): string {
  if (!entityId) return entityType
  return `${entityType} · ${entityId.slice(0, 8)}`
}

export function AuditLogPage() {
  const [entityType, setEntityType] = useState('')
  const [actorUserId, setActorUserId] = useState('')
  const [offset, setOffset] = useState(0)

  const { data, isLoading, isFetching } = useAuditLogSearch({
    entityType: entityType || undefined,
    actorUserId: actorUserId || undefined,
    limit: PAGE_SIZE,
    offset,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Audit log</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Every mutating change to patients, staff, billing, and access control — append-only, never edited.</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="entityTypeFilter">Entity type</Label>
          <Input
            id="entityTypeFilter"
            placeholder="e.g. patient, invoice"
            value={entityType}
            onChange={(e) => {
              setEntityType(e.target.value)
              setOffset(0)
            }}
            className="w-48"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="actorFilter">Actor user id</Label>
          <Input
            id="actorFilter"
            placeholder="UUID"
            value={actorUserId}
            onChange={(e) => {
              setActorUserId(e.target.value)
              setOffset(0)
            }}
            className="w-56 font-mono text-xs"
          />
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Entity</TableHead>
              <TableHead>IP</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 5 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-24" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && items.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={5}>
                  <EmptyState icon={ClipboardList} title="No audit entries" description="No changes match these filters." />
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="text-slate-500 dark:text-slate-400">{new Date(entry.created_at).toLocaleString()}</TableCell>
                  <TableCell className="text-slate-700 dark:text-slate-300">
                    {entry.actor_role ? <Badge variant="outline">{entry.actor_role}</Badge> : '—'}
                    {entry.actor_user_id && <span className="ml-1.5 font-mono text-xs text-slate-400">{entry.actor_user_id.slice(0, 8)}</span>}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-slate-700 dark:text-slate-300">{entry.action}</TableCell>
                  <TableCell className="text-slate-600 dark:text-slate-400">{formatEntity(entry.entity_type, entry.entity_id)}</TableCell>
                  <TableCell className="text-xs text-slate-400 dark:text-slate-500">{entry.ip_address || '—'}</TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0 || isFetching} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={offset + PAGE_SIZE >= total || isFetching} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
