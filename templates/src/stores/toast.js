import { reactive } from 'vue'

export const toastState = reactive({ text: '' })
let timer = null

export function toast(text) {
  toastState.text = text
  clearTimeout(timer)
  timer = setTimeout(() => { toastState.text = '' }, 3200)
}
