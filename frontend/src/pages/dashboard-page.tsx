import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/features/auth/auth-context'

// Placeholder landing page — proves the auth/query/routing skeleton works
// end to end. Real dashboard content comes in a later pass.
export function DashboardPage() {
  const { user, permissions, logout } = useAuth()

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col gap-4 p-6">
      <Card>
        <CardHeader>
          <CardTitle>
            Signed in as {user?.first_name ?? user?.email ?? user?.phone ?? 'unknown user'}
          </CardTitle>
          <CardDescription>
            Role: {user?.role_code} · Status: {user?.status}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-1.5">
            {permissions.map((code) => (
              <Badge key={code} variant="secondary">
                {code}
              </Badge>
            ))}
          </div>
          <Button variant="outline" className="self-start" onClick={() => void logout()}>
            Log out
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
