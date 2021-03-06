"""
    optimization.py

    optimization related functions from:
    NASA_LEARN_AirlineAllocation_Branch_Cut/OptimizationFiles
"""

import numpy as np
import copy

# choose a liner program solver ('linprog' or 'lpsolve')
# Note: as of this writing there is a bug in linprog that results in
#       an incorrect answer, therefore 'lpsolve' is recommended until
#       the bug is fixed (see linear_problem.py)
solver = 'lpsolve'

if solver == 'linprog':
    try:
        from scipy.optimize import linprog
    except ImportError, e:
        print "SciPy version >= 0.15.0 is required for linprog support!!"
elif solver == 'lpsolve':
    try:
        from lpsolve55 import *
    except ImportError:
        print 'lpsolve is not available'
else:
    print 'You must choose an available LP solver'
    exit(1)

np.set_printoptions(linewidth=240)


def get_objective(data):
    """ generate the objective matrix for linprog
        returns the coefficients for the integer and continuous design variables
    """

    J = data.inputs.DVector.shape[0]  # number of routes
    K = len(data.inputs.AvailPax)     # number of aircraft types
    KJ = K*J

    fuelburn  = data.coefficients.Fuelburn
    docnofuel = data.coefficients.Doc
    price     = data.outputs.TicketPrice
    fuelcost  = data.constants.FuelCost

    obj_int = np.zeros((KJ, 1))
    obj_con = np.zeros((KJ, 1))

    for kk in xrange(K):
        for jj in xrange(J):
            col = kk*J + jj
            obj_int[col] = docnofuel[kk, jj] + fuelcost * fuelburn[kk, jj]
            obj_con[col] = -price[kk, jj]

    return obj_int.flatten(), obj_con.flatten()


def get_constraints(data):
    """ generate the constraint matrix/vector for linprog
    """

    J = data.inputs.DVector.shape[0]  # number of routes
    K = len(data.inputs.AvailPax)     # number of aircraft types
    KJ  = K*J
    KJ2 = KJ*2

    dem   = data.inputs.DVector[:, 1].reshape(-1, 1)
    BH    = data.coefficients.BlockTime
    MH    = data.constants.MH.reshape(-1, 1)
    cap   = data.inputs.AvailPax.flatten()
    fleet = data.inputs.ACNum.reshape(-1, 1)
    t     = data.inputs.TurnAround

    # Upper demand constraint
    A1 = np.zeros((J, KJ2))
    b1 = dem
    for jj in xrange(J):
        for kk in xrange(K):
            col = K*J + kk*J + jj
            A1[jj, col] = 1

    # Lower demand constraint
    A2 = np.zeros((J, KJ2))
    b2 = -0.2 * dem
    for jj in xrange(J):
        for kk in xrange(K):
            col = K*J + kk*J + jj
            A2[jj, col] = -1

    # Aircraft utilization constraint
    A3 = np.zeros((K, KJ2))
    b3 = np.zeros((K, 1))
    for kk in xrange(K):
        for jj in xrange(J):
            col = kk*J + jj
            A3[kk, col] = BH[kk, jj]*(1 + MH[kk, 0]) + t
        b3[kk, 0] = 12*fleet[kk]

    # Aircraft capacity constraint
    A4 = np.zeros((KJ, KJ2))
    b4 = np.zeros((KJ, 1))
    rw = 0
    for kk in xrange(K):
        for jj in xrange(J):
            col1 = kk*J + jj
            A4[rw, col1] = 0.-cap[kk]
            col2 = K*J + kk*J + jj
            A4[rw, col2] = 1
            rw = rw + 1

    A = np.concatenate((A1, A2, A3, A4))
    b = np.concatenate((b1, b2, b3, b4))
    return A, b


def gomory_cut(x, A, b, Aeq, beq):
    """ Gomory Cut (from 'GomoryCut.m')
    """
    num_des = len(x)

    slack = np.array([])
    if b.size > 0:
        slack = b - A.dot(x)
        x_up = np.concatenate((x, slack))
        Ain_com = np.concatenate((A, np.eye(len(slack))), axis=1)
    else:
        x_up = x.copy()
        Ain_com = np.array([])

    if beq.size > 0:
        Aeq_com = np.concatenate((Aeq, np.zeros((Aeq.shape[0], slack.size))))
    else:
        Aeq_com = np.array([])

    if Aeq_com.size > 0:
        Acom = np.concatenate((Ain_com, Aeq_com))
    else:
        Acom = Ain_com

    if beq.size > 0:
        bcom = np.concatenate((b, beq))
    else:
        bcom = b

    # Generate the Simplex optimal tableau
    aaa = np.where(np.subtract(x_up, 0.) > 1e-06)
    aaa = aaa[0]
    cols = len(aaa)
    rows = Acom.shape[0]
    B = np.zeros((rows, cols))
    for ii in range(cols):
        B[:, ii] = Acom[:, aaa[ii]]

    # tab = [B\Acom,B\bcom]
    # if B is square then try solve, otherwise use least squares
    if (B.shape[0] == B.shape[1]):
        try:
            B_Acom = np.linalg.solve(B, Acom)
            B_bcom = np.linalg.solve(B, bcom)
        except np.linalg.LinAlgError:  # Singular Matrix
            B_Acom = np.linalg.lstsq(B, Acom)[0]
            B_bcom = np.linalg.lstsq(B, bcom)[0]
    else:
        B_Acom = np.linalg.lstsq(B, Acom)[0]
        B_bcom = np.linalg.lstsq(B, bcom)[0]
    tab = np.concatenate((B_Acom, B_bcom), axis=1)

    # clean up tab for comparison to MATLAB
    # print 'tab: %s\n' % str(tab.shape), tab
    # aaa = np.where(np.subtract(tab, 0.) > 1e-03)
    # print 'aaa: \n', aaa
    # cols = aaa[0]
    # rows = aaa[1]
    # tab0 = np.zeros(tab.shape)
    # for col, row in zip(rows, cols):
    #     tab0[row, col] = tab[row, col]
    # print 'tab0: %s\n' % str(tab0.shape), tab0
    # tab = tab0

    # Generate cut
    # Select the row from the optimal tableau corresponding
    # to the basic design variable that has the highest fractional part
    b_end = tab[:, -1]
    aa = np.where(np.abs(np.subtract(np.round(b_end), b_end)) > 1e-06)
    if aa[0].size > 0:
        rw_sel = np.argmax(np.remainder(np.abs(b_end), 1))
    else:
        rw_sel = None

    eflag = 0

    if rw_sel is not None:
        # apply Gomory cut
        equ_cut = tab[rw_sel, :]
        lhs = np.floor(equ_cut)
        rhs = -(equ_cut - lhs)
        lhs[-1] = -lhs[-1]
        rhs[-1] = -rhs[-1]

        # cut: rhs < 0
        a_x = rhs[0:num_des]
        a_s = rhs[num_des:rhs.shape[0] - 1]
        A_new = a_x - a_s.dot(A)
        b_new = -(rhs[-1] + a_s.dot(b))

        aa = np.where(abs(A_new - 0.) <= 1e-08)
        A_new[aa] = 0
        bb = np.where(abs(b_new - 0.) <= 1e-08)
        b_new[bb] = 0

        # Update and print cut information
        if (np.sum(A_new) != 0.) and (np.sum(np.isnan(A_new)) == 0.):
            eflag = 1
            A_up = np.concatenate((A, [A_new]))
            b_up = np.concatenate((b, [b_new]))

            cut_stat = ''
            for ii in range(len(A_new)+1):
                if ii == len(A_new):
                    symbol = ' <= '
                    cut_stat = cut_stat + symbol + str(b_new[-1])
                    break
                if A_new[ii] != 0:
                    if A_new[ii] < 0:
                        symbol = ' - '
                    else:
                        if len(cut_stat) == 0:
                            symbol = ''
                        else:
                            symbol = ' + '
                    cut_stat = cut_stat + symbol + str(abs(A_new[ii])) + 'x' + str(ii)

    if eflag == 1:
        print '\nApplying cut: %s\n' % cut_stat
    else:
        A_up = A.copy()
        b_up = b.copy()
        print '\nNo cut applied!!\n'

    return A_up, b_up, eflag


def cut_plane(x, A, b, Aeq, beq, ind_con, ind_int, indeq_con, indeq_int, num_int):
    """ execute the cutting plane algorithm
        Extracts out only the integer design variables and their associated
        constrain matrices
        Important: Assumes the design vector as x = [x_integer;x_continuous]
        (from 'call_Cutplane.m')
    """
    # make sure x and b vectors are correct shape
    x = x.reshape(-1, 1)
    b = b.reshape(-1, 1)

    num_con = x.size - num_int
    x_trip = x[0:num_int]
    pax = x[num_int:]

    if b.size > 0:
        # A can subdivided into 4 matrices
        # A = [A_x_con, A_pax_con;
        #      A_x_int, A_pax_int]
        A_x_int   = A[ind_int, 0:num_int]
        A_pax_int = A[ind_int, num_int:A.shape[1]]
        b_x_int   = b[ind_int] - A_pax_int.dot(pax)
    else:
        A_x_int = np.array([])
        b_x_int = np.array([])

    if beq.size > 0:
        Aeq_x_int   = Aeq[indeq_int, 0:num_int]
        Aeq_pax_int = Aeq[indeq_int, num_int:Aeq.shape[1]]
        beq_x_int   = beq[indeq_int] - Aeq_pax_int.dot(pax)
    else:
        Aeq_x_int = np.array([])
        beq_x_int = np.array([])

    A_x_int_up, b_x_int_up, eflag = gomory_cut(x_trip, A_x_int, b_x_int, Aeq_x_int, beq_x_int)

    if eflag == 1:
        A_new = np.concatenate((A_x_int_up[-1, :], np.ones(num_con)))
        b_new = b_x_int_up[-1] + np.ones((1, num_con)).dot(pax)
    else:
        A_new = np.array([])
        b_new = np.array([])

    A_up = np.concatenate((A, [A_new]))
    b_up = np.concatenate((b, b_new))
    return A_up, b_up


def branch_cut(f_int, f_con, A, b, Aeq, beq, lb, ub, ind_conCon, ind_intCon, indeq_conCon, indeq_intCon):
    """ This is the branch and cut algorithm

        INPUTS:
            f_int, f_con - linear objective coefficents for the integer type and
            continuous type design variables

            A, b - Coefficient matrix for linear inequality constraints Ax <= b

            Aeq, beq - Coefficient matrix for linear equality constraints Aeqx = beq

            lb, ub - Lower and upper bounds on the design variables

            ind_conCon - indices in the A matrix correspoding to the
            constraints containing only continuous type design variables

            ind_intCon - indices in the A matrix correspoding to the
            constraints containing integer and continuous (if any) type design variables

        OUTPUTS:
            xopt - optimal x with integer soltuion.
            fopt - optimal objective funtion value
            can_x - list of candidate solutions x that are feasible (i.e satisfies integer constraint)
            can_F - Corresponding list of objective function values
            x_best_relax - x value of the relaxed problem (i.e no integer constraint)
            f_best_relax - Objective fucntion value of the relaxed problem
            funCall -  total number of times the optimizer is executed
            eflag -  status of the run. 1- Solution exists. 0 - no solution found

        (from 'branch_cut.m')
    """

    f = np.concatenate((f_int, f_con))
    num_int = len(f_int)

    _iter = 0
    funCall = 0
    eflag = 0
    U_best = np.inf
    xopt = []
    fopt = []
    can_x = []
    can_F = []
    ter_crit = 0
    opt_cr = 0.03
    node_num = 1
    tree = 1

    class Problem(object):
        pass

    prob = Problem()
    prob.f    = f
    prob.A    = A
    prob.b    = b
    prob.Aeq  = Aeq
    prob.beq  = beq
    prob.lb   = lb
    prob.ub   = ub
    prob.b_F  = 0
    prob.x_F  = []
    prob.node = node_num
    prob.tree = tree

    Aset = []
    Aset.append(prob)

    while len(Aset) > 0 and ter_crit != 2:
        _iter = _iter + 1

        # pick a subproblem
        # preference given to nodes with higher objective value
        Fsub = -np.inf
        for ii in range(len(Aset)):
            if Aset[ii].b_F >= Fsub:
                Fsub_i = ii
                Fsub = Aset[ii].b_F

        if solver == 'linprog':
            # solve subproblem using linprog
            bounds = zip(Aset[Fsub_i].lb.flatten(), Aset[Fsub_i].ub.flatten())
            results = linprog(Aset[Fsub_i].f,
                              A_eq=None,           b_eq=None,
                              A_ub=Aset[Fsub_i].A, b_ub=Aset[Fsub_i].b,
                              bounds=bounds,
                              options={ 'maxiter': 1000, 'disp': True })

            Aset[Fsub_i].x_F = results.x
            Aset[Fsub_i].b_F = results.fun

            # translate status to MATLAB equivalent exit flag
            if results.status == 0:         # optimized
                Aset[Fsub_i].eflag = 1
            elif results.status == 1:       # max iterations
                Aset[Fsub_i].eflag = 0
            elif results.status == 2:       # infeasible
                Aset[Fsub_i].eflag = -2
            elif results.status == 3:       # unbounded
                Aset[Fsub_i].eflag = -3
            else:
                Aset[Fsub_i].eflag = -1
        elif solver == 'lpsolve':
            # solve using lpsolve
            obj = Aset[Fsub_i].f.tolist()
            lp = lpsolve('make_lp', 0, len(obj))
            lpsolve('set_verbose', lp, 'IMPORTANT')
            lpsolve('set_obj_fn', lp, obj)

            i = 0
            for con in Aset[Fsub_i].A:
                lpsolve('add_constraint', lp, con.tolist(), 'LE', Aset[Fsub_i].b[i])
                i = i+1

            for i in range (len(Aset[Fsub_i].lb)):
                lpsolve('set_lowbo', lp, i+1,  Aset[Fsub_i].lb[i])
                lpsolve('set_upbo',  lp, i+1, Aset[Fsub_i].ub[i])

            results = lpsolve('solve', lp)

            Aset[Fsub_i].x_F = np.array(lpsolve('get_variables', lp)[0])
            Aset[Fsub_i].b_F = np.array(lpsolve('get_objective', lp))

            # translate results to MATLAB equivalent exit flag
            if results == 0:            # optimized
                Aset[Fsub_i].eflag = 1
            elif results == 2:          # infeasible
                Aset[Fsub_i].eflag = -2
            elif results == 3:          # unbounded
                Aset[Fsub_i].eflag = -3
            else:
                Aset[Fsub_i].eflag = -1
            lpsolve('delete_lp', lp)
        else:
            print 'You must choose an available LP solver'
            exit(-1)

        funCall = funCall + 1

        # rounding integers
        if Aset[Fsub_i].eflag == 1:
            aa = np.where(np.abs(np.round(Aset[Fsub_i].x_F) - Aset[Fsub_i].x_F) <= 1e-06)
            Aset[Fsub_i].x_F[aa] = np.round(Aset[Fsub_i].x_F[aa])

            if _iter == 1:
                x_best_relax = Aset[Fsub_i].x_F
                f_best_relax = Aset[Fsub_i].b_F

        if ((Aset[Fsub_i].eflag >= 1) and (Aset[Fsub_i].b_F < U_best)):
            if np.linalg.norm(Aset[Fsub_i].x_F[range(num_int)] - np.round(Aset[Fsub_i].x_F[range(num_int)])) <= 1e-06:
                can_x = [can_x, Aset[Fsub_i].x_F]
                can_F = [can_F, Aset[Fsub_i].b_F]
                x_best = Aset[Fsub_i].x_F
                U_best = Aset[Fsub_i].b_F
                print '======================='
                print 'New solution found!'
                print '======================='
                del Aset[Fsub_i]  # Fathom by integrality
                ter_crit = 1
                if (abs(U_best - f_best_relax) / abs(f_best_relax)) <= opt_cr:
                    ter_crit = 2
            else:
                # FIXME: cut_plane is disabled for now due to inconsistent behavior
                # apply cut to subproblem
                # if Aset[Fsub_i].node != 1:
                #     Aset[Fsub_i].A, Aset[Fsub_i].b = cut_plane(
                #         Aset[Fsub_i].x_F,
                #         Aset[Fsub_i].A, Aset[Fsub_i].b,
                #         Aset[Fsub_i].Aeq, Aset[Fsub_i].beq,
                #         ind_conCon, ind_intCon,
                #         indeq_conCon, indeq_intCon,
                #         num_int
                #     )

                # branching
                x_ind_maxfrac = np.argmax(np.remainder(np.abs(Aset[Fsub_i].x_F[range(num_int)]), 1))
                x_split = Aset[Fsub_i].x_F[x_ind_maxfrac]
                print '\nBranching at tree: %d at x%d = %f\n' % (Aset[Fsub_i].tree, x_ind_maxfrac+1, x_split)
                F_sub = [None, None]
                for jj in 0, 1:
                    F_sub[jj] = copy.deepcopy(Aset[Fsub_i])
                    A_rw_add = np.zeros(len(Aset[Fsub_i].x_F))
                    if jj == 0:
                        A_con = 1
                        b_con = np.floor(x_split)
                    elif jj == 1:
                        A_con = -1
                        b_con = -np.ceil(x_split)

                    A_rw_add[x_ind_maxfrac] = A_con
                    A_up = np.concatenate((F_sub[jj].A, [A_rw_add]))
                    b_up = np.append(F_sub[jj].b, b_con)
                    F_sub[jj].A = A_up
                    F_sub[jj].b = b_up
                    F_sub[jj].tree = 10 * F_sub[jj].tree + (jj+1)
                    node_num = node_num + 1
                    F_sub[jj].node = node_num
                del Aset[Fsub_i]
                Aset.extend(F_sub)
        else:
            del Aset[Fsub_i]  # Fathomed by infeasibility or bounds

    if ter_crit > 0:
        eflag = 1
        xopt = x_best
        fopt = U_best
        if ter_crit == 1:
            print '\nSolution found but is not within %0.1f%% of the best relaxed solution!\n' % opt_cr*100
        elif ter_crit == 2:
            print '\nSolution found and is within %0.1f%% of the best relaxed solution!\n' % opt_cr*100
    else:
        print '\nNo solution found!!\n'

    return xopt, fopt, can_x, can_F, x_best_relax, f_best_relax, funCall, eflag


def generate_outputs(xopt, fopt, data):
    """ Generating Outputss from GAMS allocation solution
        (from 'OutputGen_AllCon.m')

        TODO: port of the MATLAB code... needs debugged/tested
    """

    class Outputs(object):
        pass

    outputs = Outputs()

    J = data.inputs.DVector.shape[0]  # number of routes
    K = len(data.inputs.AvailPax)     # number of aircraft types
    KJ  = K*J

    x_hat = xopt[0:KJ]                # Airline allocation variable
    aa = np.where(np.abs(x_hat - 0.) < 1e-06)[0]
    x_hat[aa] = 0

    pax = xopt[KJ:KJ*2]             # passenger design variable
    bb = np.where(np.abs(pax - 0.) < 1e-06)[0]
    pax[bb] = 0

    RVector   = data.inputs.RVector

    detailtrips = np.zeros((K, J))
    pax_rep     = np.zeros((K, J))
    for k in range(K):
        for j in range(J):
            ind = k * J + j
            detailtrips[k, j] = 2*x_hat[ind]
            pax_rep[k, j] = 2*pax[ind]

    r, c = detailtrips.shape
    outputs.DetailTrips = detailtrips

    outputs.Trips     = np.zeros((r, 1))
    outputs.FleetUsed = np.zeros((r, 1))
    outputs.Fuel      = np.zeros((r, 1))
    outputs.Doc       = np.zeros((r, 1))
    outputs.BlockTime = np.zeros((r, 1))
    outputs.Nox       = np.zeros((r, 1))
    outputs.Maxpax    = np.zeros((r, 1))
    outputs.Pax       = np.zeros((r, 1))
    outputs.Miles     = np.zeros((r, 1))

    for i in range(r):
        outputs.Trips     [i, 0] = np.sum(detailtrips[i, :])
        outputs.FleetUsed [i, 0] = np.ceil(np.sum(data.coefficients.BlockTime[i, :]*((1+data.constants.MH[i]))*(detailtrips[i, :]) + detailtrips[i, :]*(data.inputs.TurnAround)) / 24)
        outputs.Fuel      [i, 0] = np.sum(data.coefficients.Fuelburn[i, :]*(detailtrips[i, :]))
        outputs.Doc       [i, 0] = np.sum(data.coefficients.Doc[i, :]*(detailtrips[i, :]))
        outputs.BlockTime [i, 0] = np.sum(data.coefficients.BlockTime[i, :]*(detailtrips[i, :]))
        outputs.Nox       [i, 0] = np.sum(data.coefficients.Nox[i, :]*(detailtrips[i, :]))
        outputs.Maxpax    [i, 0] = np.sum(data.inputs.AvailPax[i]*(detailtrips[i, :]))
        outputs.Pax       [i, 0] = np.sum(pax_rep[i, :])
        outputs.Miles     [i, 0] = np.sum(pax_rep[i, :]*(RVector.T))

    outputs.CostDetail  = data.coefficients.Doc*detailtrips + data.coefficients.Fuelburn*data.constants.FuelCost*detailtrips
    outputs.RevDetail   = data.outputs.TicketPrice*pax_rep
    outputs.PaxDetail   = pax_rep
    outputs.RevArray    = np.sum(outputs.RevDetail, 0)
    outputs.CostArray   = np.sum(outputs.CostDetail, 0)
    outputs.PaxArray    = np.sum(pax_rep, 0)
    outputs.ProfitArray = outputs.RevArray - outputs.CostArray
    outputs.Revenue     = np.sum(outputs.RevDetail, axis=1)

    # record a/c performance
    PPNM        = np.zeros((1, K))
    ProfitArray = outputs.ProfitArray
    profit_v    = np.sum(ProfitArray.T)

    den_v = np.sum(outputs.PaxArray*RVector)
    PPNM  = np.array(profit_v / den_v)
    for i in range(PPNM.size-1):
        if np.isnan(PPNM[i]):
            PPNM[i] = 0

    outputs.Cost   = np.sum(outputs.Doc + outputs.Fuel*(data.constants.FuelCost))
    outputs.PPNM   = PPNM
    outputs.Profit = np.sum(outputs.RevArray - outputs.CostArray)

    # allocation detail info
    outputs.Info = []
    for i in range(len(RVector)):
        a = np.where(detailtrips[:, i])[0]
        info = np.array([a, detailtrips[a, i], pax_rep[a, i]])
        outputs.Info.append(info)

    return outputs


if __name__ == "__main__":

    from dataset import Dataset
    data = Dataset(suffix='after_3routes')

    # linear objective coefficients
    objective = get_objective(data)
    f_int = objective[0]    # integer type design variables
    f_con = objective[1]    # continuous type design variables

    # coefficient matrix for linear inequality constraints, Ax <= b
    constraints = get_constraints(data)
    A = constraints[0]
    b = constraints[1]

    # there are no equality constraints
    Aeq = np.ndarray(shape=(0, 0))
    beq = np.ndarray(shape=(0, 0))

    J = data.inputs.DVector.shape[0]  # number of routes
    K = len(data.inputs.AvailPax)     # number of aircraft types

    # lower and upper bounds
    lb = np.zeros((2*K*J, 1))
    ub = np.concatenate((
        np.ones((K*J, 1)) * data.inputs.MaxTrip.reshape(-1, 1),
        np.ones((K*J, 1)) * np.inf
    ))

    # indices into A matrix for continuous & integer/continuous variables
    ind_conCon = range(2*J)
    ind_intCon = range(2*J, len(constraints[0]))

    # call the branch and cut algorithm to solve the MILP problem
    xopt, fopt, can_x, can_F, x_best_relax, f_best_relax, funCall, eflag = \
        branch_cut(f_int, f_con, A, b, Aeq, beq, lb, ub,
                   ind_conCon, ind_intCon, [], [])

    print 'fopt:', fopt
    print 'xopt:\n', xopt

    # generate outputs
    outputs = generate_outputs(xopt, fopt, data)

    print
    print 'Cost:  ', outputs.Cost
    print 'PPNM:  ', outputs.PPNM
    print 'Profit:', outputs.Profit
    print
    print 'DetailTrips:\n', outputs.DetailTrips
    print 'DetailPax:  \n', outputs.PaxDetail
