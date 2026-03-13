import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.message || err.message || '请求失败'
    console.error('[API Error]', msg)
    return Promise.reject(err)
  }
)

export default api
