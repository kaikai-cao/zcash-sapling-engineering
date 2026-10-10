use bellman::{
    Circuit, ConstraintSystem, Index, LinearCombination, SynthesisError, Variable,
};
use bls12_381::Scalar;
use sapling_crypto::circuit::{Output, Spend};
use std::{error::Error, fs, path::PathBuf};

/// 只统计电路结构，不计算具体见证值，也不检查约束是否满足。
struct Counts {
    constraints: usize,
    auxiliary_variables: usize,
    input_variables: usize,
}

impl Counts {
    fn new() -> Self {
        Self {
            constraints: 0,
            auxiliary_variables: 0,
            // Bellman 将常量 ONE 计为第 0 个输入变量。
            input_variables: 1,
        }
    }
}

impl ConstraintSystem<Scalar> for Counts {
    type Root = Self;

    fn one() -> Variable {
        Variable::new_unchecked(Index::Input(0))
    }

    fn alloc<F, A, AR>(
        &mut self,
        _annotation: A,
        _f: F,
    ) -> Result<Variable, SynthesisError>
    where
        F: FnOnce() -> Result<Scalar, SynthesisError>,
        A: FnOnce() -> AR,
        AR: Into<String>,
    {
        let index = self.auxiliary_variables;
        self.auxiliary_variables += 1;

        Ok(Variable::new_unchecked(Index::Aux(index)))
    }

    fn alloc_input<F, A, AR>(
        &mut self,
        _annotation: A,
        _f: F,
    ) -> Result<Variable, SynthesisError>
    where
        F: FnOnce() -> Result<Scalar, SynthesisError>,
        A: FnOnce() -> AR,
        AR: Into<String>,
    {
        let index = self.input_variables;
        self.input_variables += 1;

        Ok(Variable::new_unchecked(Index::Input(index)))
    }

    fn enforce<A, AR, LA, LB, LC>(
        &mut self,
        _annotation: A,
        _a: LA,
        _b: LB,
        _c: LC,
    )
    where
        A: FnOnce() -> AR,
        AR: Into<String>,
        LA: FnOnce(
            LinearCombination<Scalar>,
        ) -> LinearCombination<Scalar>,
        LB: FnOnce(
            LinearCombination<Scalar>,
        ) -> LinearCombination<Scalar>,
        LC: FnOnce(
            LinearCombination<Scalar>,
        ) -> LinearCombination<Scalar>,
    {
        self.constraints += 1;
    }

    fn push_namespace<NR, N>(&mut self, _name: N)
    where
        NR: Into<String>,
        N: FnOnce() -> NR,
    {
    }

    fn pop_namespace(&mut self) {}

    fn get_root(&mut self) -> &mut Self::Root {
        self
    }
}

struct CircuitStats {
    name: &'static str,
    constraints: usize,
    auxiliary_variables: usize,
    public_inputs: usize,
    input_variables: usize,
    domain_size_estimate: usize,
}

fn measure<C: Circuit<Scalar>>(
    name: &'static str,
    circuit: C,
) -> Result<CircuitStats, SynthesisError> {
    let mut cs = Counts::new();
    circuit.synthesize(&mut cs)?;

    Ok(CircuitStats {
        name,
        constraints: cs.constraints,
        auxiliary_variables: cs.auxiliary_variables,
        public_inputs: cs.input_variables - 1,
        input_variables: cs.input_variables,
        domain_size_estimate: cs.constraints.next_power_of_two(),
    })
}

fn main() -> Result<(), Box<dyn Error>> {
    let spend = Spend {
        value_commitment_opening: None,
        proof_generation_key: None,
        payment_address: None,
        commitment_randomness: None,
        ar: None,
        auth_path: vec![None; 32],
        anchor: None,
    };

    let output = Output {
        value_commitment_opening: None,
        payment_address: None,
        commitment_randomness: None,
        esk: None,
    };

    let stats = [
        measure("Spend", spend)?,
        measure("Output", output)?,
    ];

    let mut csv = String::from(
        "circuit,constraints,auxiliary_variables,\
public_inputs_excluding_one,input_variables_including_one,\
domain_size_estimate\n",
    );

    for s in &stats {
        csv.push_str(&format!(
            "{},{},{},{},{},{}\n",
            s.name,
            s.constraints,
            s.auxiliary_variables,
            s.public_inputs,
            s.input_variables,
            s.domain_size_estimate,
        ));
    }

    // 原始测量数据统一写入 experiments/raw/csv。
    let output_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../experiments/raw/csv");

    fs::create_dir_all(&output_dir)?;

    let output_path =
        output_dir.join("sapling_circuit_scale_raw.csv");

    fs::write(&output_path, &csv)?;

    println!("{csv}");
    println!("原始 CSV 已写入：{}", output_path.display());

    Ok(())
}