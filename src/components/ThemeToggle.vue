<script setup lang="ts">
import { useTheme } from '../useTheme'

const { theme, toggle } = useTheme()
</script>

<template>
  <button
    class="theme-toggle"
    :aria-label="theme === 'light' ? '切换到深色模式' : '切换到浅色模式'"
    @click="toggle"
  >
    <span class="icon-wrapper" :class="{ 'to-dark': theme === 'light' }">
      <!-- 太阳 -->
      <svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
      </svg>
      <!-- 月亮 -->
      <svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    </span>
  </button>
</template>

<style scoped>
.theme-toggle {
  position: fixed;
  top: 14px;
  right: 16px;
  /* 位于「一级页面」层：高于顶部栏/筛选栏，但低于二级对比抽屉(400)，
     因此打开对比页时会被抽屉及其遮罩遮挡 */
  z-index: 350;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-glass);
  backdrop-filter: blur(12px) saturate(180%);
  -webkit-backdrop-filter: blur(12px) saturate(180%);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: transform var(--dur-fast) var(--ease-spring),
              box-shadow var(--dur-normal) var(--ease-smooth);
}

.theme-toggle:hover {
  transform: scale(1.1) rotate(15deg);
  box-shadow: var(--shadow-md);
}

.theme-toggle:active {
  transform: scale(0.95);
}

.icon-wrapper {
  position: relative;
  width: 20px;
  height: 20px;
}

.sun,
.moon {
  position: absolute;
  inset: 0;
  width: 20px;
  height: 20px;
  color: var(--brand);
  transition: transform var(--dur-normal) var(--ease-spring),
              opacity var(--dur-normal) var(--ease-smooth);
}

/* 浅色模式：显示太阳 */
.icon-wrapper.to-dark .sun {
  transform: rotate(0deg) scale(1);
  opacity: 1;
}

.icon-wrapper.to-dark .moon {
  transform: rotate(90deg) scale(0);
  opacity: 0;
}

/* 深色模式：显示月亮 */
.icon-wrapper:not(.to-dark) .sun {
  transform: rotate(-90deg) scale(0);
  opacity: 0;
}

.icon-wrapper:not(.to-dark) .moon {
  transform: rotate(0deg) scale(1);
  opacity: 1;
}

@media (max-width: 480px) {
  .theme-toggle {
    width: 36px;
    height: 36px;
    top: 10px;
    right: 12px;
  }
}
</style>
