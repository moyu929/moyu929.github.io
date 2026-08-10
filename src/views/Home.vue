<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { categories } from '../data'
</script>

<template>
  <div class="home">
    <header class="hero">
      <h1>家电参数横评</h1>
      <p>手工整理的家电数据库 · 参数对比 · 选购参考</p>
    </header>

    <main class="container">
      <div class="grid">
        <RouterLink v-for="c in categories" :key="c.id" class="card" :to="`/${c.id}`">
          <span class="icon" aria-hidden="true">{{ c.icon }}</span>
          <div class="body">
            <h2>{{ c.name }}</h2>
            <p>{{ c.description }}</p>
          </div>
          <span class="arrow" aria-hidden="true">›</span>
        </RouterLink>
      </div>

      <p class="note">更多品类陆续添加中</p>
    </main>
  </div>
</template>

<style scoped>
.hero {
  background: linear-gradient(135deg, var(--header-from), var(--header-to));
  color: #fff;
  padding: 40px 16px 36px;
  text-align: center;
}

.hero h1 {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 6px;
}

.hero p {
  font-size: 12px;
  opacity: 0.65;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  padding: 16px 0;
}

.card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--surface);
  border-radius: var(--radius);
  padding: 16px;
  box-shadow: var(--shadow-sm);
  transition: transform 0.15s, box-shadow 0.15s;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.icon {
  font-size: 28px;
  flex-shrink: 0;
}

.body {
  flex: 1;
  min-width: 0;
}

.body h2 {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 3px;
}

.body p {
  font-size: 11px;
  color: var(--text-faint);
  line-height: 1.5;
}

.arrow {
  font-size: 22px;
  color: var(--text-faint);
  flex-shrink: 0;
}

.note {
  text-align: center;
  font-size: 11px;
  color: var(--text-faint);
  padding: 12px 0 32px;
}

@media (min-width: 768px) {
  .hero {
    padding: 64px 16px 56px;
  }

  .hero h1 {
    font-size: 30px;
  }
}
</style>
