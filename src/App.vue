<script setup lang="ts">
import { ref } from 'vue'
import { RouterView } from 'vue-router'
import ThemeToggle from './components/ThemeToggle.vue'
import SiteNotice from './components/SiteNotice.vue'

/**
 * 右上角常驻操作组：主题切换 + 声明入口。
 * 声明原本放在页脚，页脚只留一行居中文案；两个入口现在并排，
 * 位置固定在视口右上，不随内容滚动。
 */
const noticeRef = ref<InstanceType<typeof SiteNotice> | null>(null)

function openNotice() {
  noticeRef.value?.show()
}
</script>

<template>
  <div class="corner-actions">
    <button
      class="notice-btn"
      type="button"
      aria-label="数据来源与免责声明"
      title="数据来源与免责声明"
      @click="openNotice"
    >
      <!-- 信息图标：圆圈 + i，标准的信息语义 -->
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5" />
        <path d="M12 7.6v.4" />
      </svg>
    </button>
    <ThemeToggle />
  </div>

  <RouterView v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" />
    </Transition>
  </RouterView>

  <SiteNotice ref="noticeRef" />
</template>

<style>
/* 右上角操作组容器。ThemeToggle 自带 position: fixed，
   这里只负责把声明按钮放到它左边，两者各自定位。 */
.corner-actions {
  position: fixed;
  top: 14px;
  right: 16px;
  /* 位于「一级页面」层：高于顶部栏/筛选栏，但低于二级对比抽屉(400) */
  z-index: 350;
  display: flex;
  align-items: center;
  gap: 8px;
}

.corner-actions .notice-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  background: var(--surface);
  color: var(--text-muted);
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease-smooth),
    color var(--dur-fast) var(--ease-smooth),
    border-color var(--dur-fast) var(--ease-smooth);
}

.corner-actions .notice-btn:hover {
  background: var(--surface-hover);
  border-color: var(--border-brand);
  color: var(--brand);
}

.corner-actions .notice-btn:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}

.corner-actions .notice-btn svg {
  width: 19px;
  height: 19px;
}

/* ThemeToggle 已在外层定位，这里放开让 flex 定位接管 */
.corner-actions > .theme-toggle {
  position: static;
}

/* 页面切换过渡 */
.page-enter-active {
  transition: opacity var(--dur-slow) var(--ease-out),
              transform var(--dur-slow) var(--ease-out);
}

.page-leave-active {
  transition: opacity var(--dur-fast) var(--ease-smooth),
              transform var(--dur-fast) var(--ease-smooth);
}

.page-enter-from {
  opacity: 0;
  transform: translateY(16px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>