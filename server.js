// Setup dell'ambiente e delle librerie necessarie
require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const { ethers } = require('ethers');

const app = express();
const port = process.env.PORT || 3000;

// Configurazione del middleware per il parsing JSON
app.use(bodyParser.json());
app.use(express.static('static'));

// Configurazione del provider Ethereum e del wallet di distribuzione
const provider = new ethers.providers.JsonRpcProvider(process.env.PROVIDER_URL);
const wallet = new ethers.Wallet(process.env.DISTRIBUTION_PRIVATE_KEY, provider);

// Interazione con il contratto del token
const tokenAddress = process.env.TOKEN_ADDRESS;
const tokenABI = [
    "function transfer(address to, uint amount) returns (bool)"
];
const tokenContract = new ethers.Contract(tokenAddress, tokenABI, wallet);

// Endpoint per gestire il giro della ruota e la distribuzione dei premi
app.post('/api/spin', async (req, res) => {
    const { wallet_address } = req.body;

    if (!wallet_address) {
        return res.status(400).json({ error: "Wallet address is required" });
    }

    // Simulazione della logica per determinare il premio
    const prize = determinePrize();
    console.log(`Prize determined: ${prize}`);

    // Trasferimento dei token se il premio è in GKY
    if (prize !== "NO PRIZE") {
        const prizeAmount = ethers.utils.parseUnits(prize, 18); // Assumendo che il premio sia un numero di token
        try {
            const tx = await tokenContract.transfer(wallet_address, prizeAmount);
            await tx.wait();
            console.log(`Tokens transferred: ${prize} to ${wallet_address}`);
            res.json({ message: "Prize transferred successfully", txid: tx.hash });
        } catch (error) {
            console.error("Failed to transfer prize:", error);
            res.status(500).json({ error: "Failed to transfer prize" });
        }
    } else {
        res.json({ message: "No prize won this time." });
    }
});

// Funzione per determinare il premio
function determinePrize() {
    const rand = Math.random();
    if (rand < 0.1) return "1000 GKY"; // Esempio di probabilità
    else if (rand < 0.2) return "500 GKY";
    else if (rand < 0.5) return "100 GKY";
    else if (rand < 0.7) return "50 GKY";
    else if (rand < 0.9) return "20 GKY";
    else return "NO PRIZE";
}

app.listen(port, () => {
    console.log(`Server listening on port ${port}`);
});
