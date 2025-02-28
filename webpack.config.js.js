const path = require('path');

module.exports = {
  entry: './src/main.js',  // Il file di ingresso deve essere src/main.js
  output: {
    filename: 'bundle.js', // Il bundle finale verrà generato in dist/
    path: path.resolve(__dirname, 'dist')
  },
  mode: 'development', // Usa "production" per build ottimizzate
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: ['@babel/preset-env']
          }
        }
      }
    ]
  },
  resolve: {
    fallback: {
      "stream": require.resolve("stream-browserify"),
      "assert": require.resolve("assert"),
      "util": require.resolve("util"),
      "http": require.resolve("stream-http"),
      "https": require.resolve("https-browserify"),
      "os": require.resolve("os-browserify/browser"),
      "url": require.resolve("url")
    }
  }
};
