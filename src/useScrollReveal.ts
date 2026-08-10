import { onMounted, onBeforeUnmount } from 'vue'

/**
 * 滚动揭示动画：元素进入视口时添加 .revealed 类
 * 用法：在模板根元素或子元素上加 class="reveal"
 *       调用 useScrollReveal() 即可自动监听
 */
export function useScrollReveal() {
  let observer: IntersectionObserver | null = null

  function setup() {
    // 先清理旧的 observer，避免重复观察和内存泄漏
    observer?.disconnect()

    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('revealed')
            observer?.unobserve(entry.target)
          }
        }
      },
      { threshold: 0.08, rootMargin: '0px 0px -40px 0px' },
    )

    // 延迟一帧确保 DOM 已渲染
    requestAnimationFrame(() => {
      document.querySelectorAll('.reveal:not(.revealed)').forEach((el) => {
        observer?.observe(el)
      })
    })
  }

  onMounted(() => {
    setup()
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
  })

  return { setup }
}
