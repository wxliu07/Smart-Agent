import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'


export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 8090,
    // 是否开启 https
    https: false,
      // 设置反向代理，跨域
      proxy: {
        '/api': {
          target: 'http://localhost:7860/',
          changeOrigin: true,
      }
    },
  },

  css: {
    preprocessorOptions: {
      scss: {
        // 方法1：升级到 modern API（推荐）
        // api: 'modern',
        
        // 方法2：如果要用 legacy，静默警告
        silenceDeprecations: ['legacy-js-api'],
      }
    }
  },

  plugins: [vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  
})
