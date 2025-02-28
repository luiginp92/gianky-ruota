const path = require('path');

module.exports = {
  entry: './src/main.js', // Il punto di ingresso del codice frontend
  output: {
    filename: 'bundle.js', // Il bundle finale
    path: path.resolve(__dirname, 'dist')
  },
  mode: 'development', // Cambia in "production" per build ottimizzate
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: ['@babel/preset-env'] // Per convertire ES6+ in ES5
          }
        }
      }
    ]
  }
};
