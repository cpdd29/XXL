import { AppHeader } from "@/shared/layout/app-header"
import { AppSidebar } from "@/shared/layout/app-sidebar"
import { AuthGuard } from "@/shared/providers/auth-guard"

export default function ToolsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AuthGuard>
      <div className="flex h-screen bg-background">
        <AppSidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <AppHeader />
          <main className="flex min-h-0 flex-1 overflow-hidden">{children}</main>
        </div>
      </div>
    </AuthGuard>
  )
}
