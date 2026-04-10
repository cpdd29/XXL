import { AppSidebar } from "@/components/layout/app-sidebar"
import { AppHeader } from "@/components/layout/app-header"
import { AuthGuard } from "@/components/providers/auth-guard"

export default function WorkflowLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AuthGuard>
      <div className="flex h-screen bg-background">
        <AppSidebar />
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <AppHeader />
          <main className="min-h-0 flex-1 overflow-auto">{children}</main>
        </div>
      </div>
    </AuthGuard>
  )
}
