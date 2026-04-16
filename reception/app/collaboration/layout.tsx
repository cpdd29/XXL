import { AppSidebar } from "@/components/layout/app-sidebar"
import { AuthGuard } from "@/components/providers/auth-guard"

export default function CollaborationLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AuthGuard>
      <div className="flex h-screen bg-background">
        <AppSidebar />
        <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
      </div>
    </AuthGuard>
  )
}
