module.exports = {
    chainWebpack: config => {
      config.module
        .rule('js')
        .use('babel-loader')
        .loader('babel-loader')
        .tap(options => {
          // 初始化 options 对象和 plugins 数组
          options = options || {};
          options.plugins = options.plugins || [];
          // 添加正确的插件名称（注意拼写）
          options.plugins.push('@babel/plugin-proposal-optional-chaining');
          return options;
        });
    },
    lintOnSave: false,
    devServer: {
      overlay: {
        warnings: false,
        errors: false
      },
      proxy: {
        '/datasets': {
          target: 'http://localhost:5000',
          changeOrigin: true
        },
        '/api': {
          target: 'http://localhost:5000',
          changeOrigin: true
        }
      }
    },
    productionSourceMap: false,
    css: {
      loaderOptions: {
        sass: {
          // 全局导入变量和混合
          prependData: `
            @import "@/assets/styles/variables.scss";
            @import "@/assets/styles/mixins.scss";
          `
        }
      }
    }
  }