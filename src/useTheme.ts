import { onMounted, ref, watch } from 'vue'

type Theme = 'light' | 'dark'

const STORAGE_KEY = 'app-theme'
const theme = ref<Theme>('light')
let initialized = false

/** 从 localStorage 或系统偏好读取初始主题 */
function resolveInitial(): Theme {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** 将主题应用到 <html data-theme="..."> */
function applyTheme(t: Theme) {
  document.documentElement.setAttribute('data-theme', t)
}

/** 初始化（仅执行一次）：读取偏好 + 监听系统变化 */
function init() {
  if (initialized) return
  initialized = true

  theme.value = resolveInitial()
  applyTheme(theme.value)

  // 系统主题变化时，若用户未手动设定则跟随
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      theme.value = e.matches ? 'dark' : 'light'
    }
  })
}

/** 主题管理 composable */
export function useTheme() {
  onMounted(() => init())

  watch(theme, (t) => {
    applyTheme(t)
    localStorage.setItem(STORAGE_KEY, t)
  })

  function toggle() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  return { theme, toggle }
}
