<script setup lang="ts">
import { RouterView } from 'vue-router'
import ThemeToggle from './components/ThemeToggle.vue'
import SiteNotice from './components/SiteNotice.vue'
</script>

<template>
  <ThemeToggle />
  <RouterView v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" />
    </Transition>
  </RouterView>
  <SiteNotice />
</template>

<style>
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
