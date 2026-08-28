'use client'

import Link from 'next/link'
import {SidebarTrigger, useSidebar} from '@/components/ui/sidebar'
import {ManusSettings} from '@/components/manus-settings'
import {ManusIcon} from '@/components/manus-icon'

export function ChatHeader() {
  const {open, isMobile} = useSidebar()

  return (
    <header className="flex justify-between items-center w-full py-2 px-4 z-50">
      {/* 左侧操作&logo */}
      <div className="flex items-center gap-2">
        {/* 面板操作按钮: 关闭面板&移动端下会显示 */}
        {(!open || isMobile) && <SidebarTrigger className="cursor-pointer"/>}
        <Link
          href="/"
          aria-label="返回 MoocManus 首页"
          className="flex items-center justify-center bg-white w-[80px] h-9 rounded-md border"
        >
          <ManusIcon/>
        </Link>
      </div>
      {/* 右侧设置模态窗 */}
      <ManusSettings/>
    </header>
  )
}
