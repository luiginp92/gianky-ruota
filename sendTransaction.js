const Web3 = require('web3');
const web3 = new Web3('https://polygon-rpc.com');

// Dati per la transazione
const senderAddress = '0xBc0c054066966a7A6C875981a18376e2296e5815';
const privateKey = '9a1aaf6ca8dc9f5d02c9a8f526f97667b360cbf1'; // Senza '0x' come stringa
const recipientAddress = '0x4ec983b240535be1592d8B4c2EfA065bF9a87fBb';
const contractAddress = '0x370806781689E670f85311700445449aC7C3Ff7a';
const amount = web3.utils.toWei('50000', 'ether');  // Imposta l'importo in wei

// Contratto ERC20 ABI minimale per il trasferimento
const contract = new web3.eth.Contract([
  {
    "constant": false,
    "inputs": [
      { "name": "to", "type": "address" },
      { "name": "value", "type": "uint256" }
    ],
    "name": "transfer",
    "outputs": [{ "name": "", "type": "bool" }],
    "payable": false,
    "stateMutability": "nonpayable",
    "type": "function"
  }
], contractAddress);

// Converti la chiave privata in un Uint8Array (assicurati che non abbia '0x' davanti)
const privateKeyBuffer = Buffer.from(privateKey, 'hex');

// Ottieni il nonce per la transazione
web3.eth.getTransactionCount(senderAddress).then(nonce => {
  // Definisci la transazione
  const tx = {
    from: senderAddress,
    to: contractAddress,
    gas: 200000,
    gasPrice: web3.utils.toWei('30', 'gwei'),
    nonce: nonce,
    data: contract.methods.transfer(recipientAddress, amount).encodeABI()
  };

  // Firma la transazione (la chiave privata è passata come un Buffer)
  web3.eth.accounts.signTransaction(tx, privateKeyBuffer).then(signedTx => {
    // Invia la transazione firmata
    web3.eth.sendSignedTransaction(signedTx.rawTransaction)
      .on('receipt', console.log)
      .on('error', console.error);
  }).catch(console.error);
}).catch(console.error);
