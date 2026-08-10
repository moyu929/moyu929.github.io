<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { categories } from '../data'
import { useScrollReveal } from '../useScrollReveal'

useScrollReveal()
</script>

<template>
  <div class="home">
    <!-- 动画 Hero -->
    <header class="hero">
      <div class="hero-bg" aria-hidden="true">
        <span class="orb orb-1"></span>
        <span class="orb orb-2"></span>
        <span class="orb orb-3"></span>
      </div>

      <div class="hero-content">
        <div class="badge">
          <span class="dot"></span>
          持续更新中
        </div>
        <h1>
          <span class="hero-title-line" style="animation-delay: 0.1s">家电参数</span>
          <span class="hero-title-line gradient" style="animation-delay: 0.25s">横评数据库</span>
        </h1>
        <p class="subtitle" style="animation-delay: 0.4s">
          手工整理的家电参数 · 多维对比 · 选购参考
        </p>
      </div>
    </header>

    <!-- 品类卡片 -->
    <main class="container">
      <div class="section-head">
        <h2>浏览品类</h2>
        <span class="count">{{ categories.length }} 个品类</span>
      </div>

      <div class="grid">
        <RouterLink
          v-for="(c, i) in categories"
          :key="c.id"
          class="card reveal"
          :to="`/${c.id}`"
          :style="{ transitionDelay: `${i * 0.1}s` }"
        >
          <div class="card-icon">
            <span aria-hidden="true">{{ c.icon }}</span>
          </div>
          <div class="card-body">
            <h3>{{ c.name }}</h3>
            <p>{{ c.description }}</p>
          </div>
          <div class="card-arrow" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </div>
          <div class="card-glow" aria-hidden="true"></div>
        </RouterLink>
      </div>

      <p class="note">更多品类陆续添加中</p>
    </main>
  </div>
</template>

<style scoped>
/* ============ Hero ============ */
.hero {
  position: relative;
  background: var(--header-gradient);
  background-size: 200% 200%;
  color: var(--header-text);
  padding: 80px 16px 72px;
  text-align: center;
  overflow: hidden;
  animation: gradientFlow 12s ease infinite;
}

.hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
}

.orb-1 {
  width: 300px;
  height: 300px;
  background: var(--header-orb-1);
  top: -60px;
  left: -40px;
  animation: orbDrift1 16s ease-in-out infinite;
}

.orb-2 {
  width: 250px;
  height: 250px;
  background: var(--header-orb-2);
  bottom: -50px;
  right: -30px;
  animation: orbDrift2 20s ease-in-out infinite;
}

.orb-3 {
  width: 200px;
  height: 200px;
  background: var(--header-orb-3);
  top: 40%;
  left: 60%;
  animation: orbDrift3 24s ease-in-out infinite;
}

.hero-content {
  position: relative;
  z-index: 1;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--header-surface);
  backdrop-filter: blur(8px);
  border: 1px solid var(--header-surface-border);
  border-radius: var(--radius-full);
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--header-text);
  margin-bottom: 20px;
  animation: fadeInUp 0.6s var(--ease-out) both;
}

.badge .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #51cf66;
  animation: pulse 2s ease infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}

.hero h1 {
  font-size: 36px;
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: -0.02em;
  margin-bottom: 12px;
}

.hero-title-line {
  display: block;
  animation: fadeInUp 0.7s var(--ease-out) both;
}

.hero-title-line.gradient {
  background: linear-gradient(135deg, var(--brand), var(--brand-light), var(--brand));
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: fadeInUp 0.7s var(--ease-out) both,
             gradientFlow 4s linear infinite;
}

.subtitle {
  font-size: 14px;
  color: var(--header-text-muted);
  animation: fadeInUp 0.7s var(--ease-out) both;
}

/* ============ Section ============ */
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 32px 0 16px;
  animation: fadeInUp 0.6s var(--ease-out) 0.5s both;
}

.section-head h2 {
  font-size: 20px;
  font-weight: 700;
}

.count {
  font-size: 12px;
  color: var(--text-faint);
  font-weight: 500;
}

.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  padding-bottom: 16px;
}

/* ============ 品类卡片 ============ */
.card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: transform var(--dur-normal) var(--ease-out),
              box-shadow var(--dur-normal) var(--ease-smooth),
              border-color var(--dur-normal) var(--ease-smooth);
}

.card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
  border-color: var(--border-brand);
}

.card:hover .card-glow {
  opacity: 1;
}

.card:hover .card-icon {
  transform: scale(1.1) rotate(-5deg);
}

.card:hover .card-arrow {
  transform: translateX(4px);
  opacity: 1;
}

.card-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-sm);
  background: var(--brand-surface);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  flex-shrink: 0;
  transition: transform var(--dur-normal) var(--ease-spring);
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-body h3 {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 4px;
}

.card-body p {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}

.card-arrow {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  color: var(--brand);
  opacity: 0.5;
  transition: transform var(--dur-normal) var(--ease-out),
              opacity var(--dur-normal) var(--ease-smooth);
}

.card-arrow svg {
  width: 100%;
  height: 100%;
}

.card-glow {
  position: absolute;
  top: 0;
  left: 0;
  width: 200px;
  height: 100%;
  background: linear-gradient(90deg, var(--brand-soft), transparent);
  opacity: 0;
  transition: opacity var(--dur-slow) var(--ease-smooth);
  pointer-events: none;
}

/* ============ 底部提示 ============ */
.note {
  text-align: center;
  font-size: 12px;
  color: var(--text-faint);
  padding: 20px 0 48px;
}

/* ============ 响应式 ============ */
@media (min-width: 640px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 768px) {
  .hero {
    padding: 120px 24px 100px;
  }

  .hero h1 {
    font-size: 48px;
  }

  .subtitle {
    font-size: 16px;
  }

  .grid {
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
  }

  .card {
    padding: 24px;
  }

  .card-icon {
    width: 64px;
    height: 64px;
    font-size: 34px;
  }

  .card-body h3 {
    font-size: 18px;
  }

  .card-body p {
    font-size: 13px;
  }
}

@media (min-width: 1024px) {
  .hero h1 {
    font-size: 56px;
  }
}
</style>
