import { AppSidebar } from "@/shared/layout/app-sidebar"
import { AppHeader } from "@/shared/layout/app-header"
import { AuthGuard } from "@/shared/providers/auth-guard"

export default function SecurityLayout({
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
          <main className="flex-1 overflow-auto">{children}</main>
        </div>
      </div>
    </AuthGuard>
  )
}
